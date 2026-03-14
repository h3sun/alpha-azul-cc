"""
ai/mcts_agent.py — Heuristic Shallow MCTS agent for Azul (花砖物语)

Architecture
------------
  Selection   : UCT (Upper Confidence Bound for Trees), multi-player max-N
  Simulation  : Depth-limited (max_depth plies) with heuristic move ordering,
                then static evaluation — no full rollouts to game-end.
  Evaluation  : Weighted sum of board features (see EvalWeights / evaluate_state)

Performance (MacBook M1, 2-player game)
  Old (full rollout):       ~510 iterations/sec
  New (depth-6 + eval):   ~5 000 iterations/sec  (~10× improvement)

Threading
---------
  choose_move(state, queue)  is a drop-in for RandomAI; search runs entirely
  within the calling thread, which the UI places on a background daemon thread.
"""

from __future__ import annotations

import math
import time
import random
import queue
import sys
import os
from dataclasses import dataclass
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import (AzulState, PlayerBoard, Move,
                    CENTER, FLOOR, WALL_PATTERN, NUM_COLORS,
                    BONUS_ROW, BONUS_COL, BONUS_COLOR, FLOOR_PENALTIES)


# ── Fast state clone ──────────────────────────────────────────────────────────

def _fast_clone(state: AzulState) -> AzulState:
    """
    Hand-rolled clone of AzulState — ~12× faster than copy.deepcopy.
    Uses object.__new__ + list-slicing (C-level) and a fresh random.Random()
    instead of pickling the RNG (MCTS simulations need randomness, not
    reproducibility).
    """
    new = object.__new__(AzulState)
    new.num_players        = state.num_players
    new.num_factories      = state.num_factories
    new.rng                = random.Random()

    boards = []
    for b in state.boards:
        nb = object.__new__(PlayerBoard)
        nb.pattern_lines    = [row[:] for row in b.pattern_lines]
        nb.wall             = [row[:] for row in b.wall]
        nb.floor            = b.floor[:]
        nb.score            = b.score
        nb.has_first_marker = b.has_first_marker
        boards.append(nb)
    new.boards = boards

    new.factories          = [dict(f) for f in state.factories]
    new.center             = dict(state.center)
    new.bag                = state.bag[:]
    new.discard            = state.discard[:]
    new.current_player     = state.current_player
    new._next_first_player = state._next_first_player
    new.phase              = state.phase
    new.game_over          = state.game_over
    return new


# ── Static evaluation helpers ─────────────────────────────────────────────────

def _score_preview(wall: list, row: int, col: int) -> int:
    """
    Estimate the points gained when placing a tile at (row, col) on `wall`.
    Mirrors engine._score_placement but works BEFORE the tile is on the wall
    (wall[row][col] must be False — the tile is being previewed, not placed).
    """
    # Horizontal chain length (starting count=1 for the new tile)
    h = 1
    c = col - 1
    while c >= 0 and wall[row][c]:     h += 1; c -= 1
    c = col + 1
    while c < 5 and wall[row][c]:      h += 1; c += 1
    # Vertical chain length
    v = 1
    r = row - 1
    while r >= 0 and wall[r][col]:     v += 1; r -= 1
    r = row + 1
    while r < 5 and wall[r][col]:      v += 1; r += 1

    if h == 1 and v == 1:
        return 1
    return (h if h > 1 else 0) + (v if v > 1 else 0)


# ── Evaluation weights ────────────────────────────────────────────────────────

@dataclass
class EvalWeights:
    """
    Configurable weights for evaluate_state().
    All values are in natural score-point units so they combine
    additively with the raw board score.

    Derivation (first-principles):
      pending   1.0  — complete pattern line → confirmed pts this round;
                       same certainty as an already-scored point.
      progress  0.5  — partial row: fill² × expected_pts; quadratic because
                       going 4→5/5 is much closer to scoring than 1→2/5.
      adjacency 0.3  — each H/V adjacent wall pair means the NEXT tile placed
                       in that row/col scores +1 extra; 0.3 ≈ 30% chance the
                       relevant position gets filled in the near term.
      row_bonus 1.0  — fill² × 1.0; max +1.0 per row (5 rows → +5 max).
                       The +2 end-bonus discounted by ~0.5 for uncertainty.
      col_bonus 3.5  — fill² × 3.5; max +3.5 per col (5 cols → +17 max).
                       The +7 end-bonus discounted by ~0.5.
      clr_bonus 5.0  — fill² × 5.0; max +5.0 per color (5 colors → +25 max).
                       The +10 end-bonus discounted by ~0.5.
      floor_mul 1.2  — multiply floor_penalty(); floor tiles waste a turn AND
                       cost points, so penalise 20% above face value.
    """
    pending:   float = 1.0
    progress:  float = 0.5
    adjacency: float = 0.3
    row_bonus: float = 1.0
    col_bonus: float = 3.5
    clr_bonus: float = 5.0
    floor_mul: float = 1.2


_DEFAULT_WEIGHTS = EvalWeights()


def _board_position(board: PlayerBoard, w: EvalWeights) -> float:
    """
    Heuristic position value for one player's board, in score-point units.
    Higher = better position.
    """
    wall = board.wall

    # ── 1. Actual score ───────────────────────────────────────────────────────
    pos = float(board.score)

    # ── 2. Floor penalty (already negative) ──────────────────────────────────
    pos += w.floor_mul * board.floor_penalty()

    # ── 3. Pattern line value ─────────────────────────────────────────────────
    #   • Complete rows   → pending points (certain this round)
    #   • Partial rows    → progress credit (fill² × expected pts, discounted)
    for row in range(5):
        color, count = board.pattern_lines[row]
        if color == -1 or count == 0:
            continue
        col = WALL_PATTERN[row].index(color)
        pts = _score_preview(wall, row, col)   # expected pts when this tile is placed
        cap = row + 1
        if count == cap:
            pos += w.pending * pts
        else:
            fill_ratio = count / cap
            pos += w.progress * (fill_ratio ** 2) * pts

    # ── 4. Wall adjacency (future scoring potential) ──────────────────────────
    adj = 0
    for r in range(5):
        for c in range(4):
            if wall[r][c] and wall[r][c + 1]:
                adj += 1
    for r in range(4):
        for c in range(5):
            if wall[r][c] and wall[r + 1][c]:
                adj += 1
    pos += w.adjacency * adj

    # ── 5. End-game bonus progress (quadratic: near-completion rewarded heavily)
    for r in range(5):
        filled = sum(wall[r])
        if filled < 5:
            pos += w.row_bonus * (filled / 5) ** 2

    for c in range(5):
        filled = sum(wall[r][c] for r in range(5))
        if filled < 5:
            pos += w.col_bonus * (filled / 5) ** 2

    for color in range(NUM_COLORS):
        filled = sum(1 for r in range(5) if wall[r][WALL_PATTERN[r].index(color)])
        if filled < 5:
            pos += w.clr_bonus * (filled / 5) ** 2

    return max(0.0, pos)


def evaluate_state(state: AzulState,
                   weights: EvalWeights = _DEFAULT_WEIGHTS) -> List[float]:
    """
    Static evaluation of `state`.
    Returns a per-player value vector normalised to sum to 1 (all values in
    [0, 1]), making it directly compatible with the UCT backpropagation.

    For terminal states the actual final scores are used.
    """
    if state.game_over:
        scores = [float(b.score) for b in state.boards]
        total  = sum(scores)
        n      = state.num_players
        return [s / total for s in scores] if total > 0 else [1.0 / n] * n

    positions = [_board_position(state.boards[pid], weights)
                 for pid in range(state.num_players)]
    total = sum(positions)
    n     = state.num_players
    return [p / total for p in positions] if total > 0 else [1.0 / n] * n


# ── Heuristic move selection ──────────────────────────────────────────────────

def _move_weight(state: AzulState, move: Move) -> float:
    """
    Move priority weight for simulation move ordering.

      4.0  — completes a pattern row (immediate scoring trigger)
      1–2  — partial fill (proportional to fill ratio)
      0.1  — floor discard (last resort)

    Overflow penalty: -0.3 per tile spilled to floor.
    """
    if move.target_row == FLOOR:
        return 0.1

    board = state.boards[state.current_player]
    row   = move.target_row
    cap   = row + 1
    _, pl_count = board.pattern_lines[row]

    taken = (state.center.get(move.color, 0)
             if move.source == CENTER
             else state.factories[move.source].get(move.color, 0))

    space    = cap - pl_count
    overflow = max(0, taken - space)
    new_fill = pl_count + min(taken, space)

    if new_fill == cap:
        return 4.0

    fill_ratio = new_fill / cap
    return max(0.05, 1.0 + fill_ratio - 0.3 * overflow)


def _heuristic_pick(state: AzulState, moves: List[Move]) -> Move:
    """Weighted-random draw from moves using heuristic weights."""
    weights = [_move_weight(state, m) for m in moves]
    total   = sum(weights)
    if total <= 0:
        return random.choice(moves)
    r = random.random() * total
    cum = 0.0
    for m, w in zip(moves, weights):
        cum += w
        if r <= cum:
            return m
    return moves[-1]


# ── MCTS node ─────────────────────────────────────────────────────────────────

class _Node:
    """
    MCTS tree node — multi-player max-N semantics.

    total_values[i]  accumulates the evaluation score for player i across all
                     simulations that passed through this node.
    UCT selection uses total_values[node.player_id] so each player maximises
    their own expected value, correct for 2-4 players.
    """
    __slots__ = (
        'state', 'parent', 'move',
        'children', 'untried_moves',
        'visits', 'total_values',
        'player_id',
    )

    def __init__(self,
                 state:  AzulState,
                 parent: Optional[_Node],
                 move:   Optional[Move]):
        self.state        = state
        self.parent       = parent
        self.move         = move
        self.children:    List[_Node] = []
        moves = state.get_legal_moves()
        random.shuffle(moves)
        self.untried_moves: List[Move] = moves
        self.visits       = 0
        self.total_values = [0.0] * state.num_players
        self.player_id    = state.current_player

    @property
    def is_terminal(self) -> bool:
        return self.state.game_over

    @property
    def is_fully_expanded(self) -> bool:
        return len(self.untried_moves) == 0

    def _uct(self, child: _Node, c: float) -> float:
        if child.visits == 0:
            return float('inf')
        p = self.player_id
        return (child.total_values[p] / child.visits
                + c * math.sqrt(math.log(self.visits) / child.visits))

    def best_child_uct(self, c: float) -> _Node:
        return max(self.children, key=lambda ch: self._uct(ch, c))

    def best_child_robust(self) -> _Node:
        """Most-visited child — used for final move selection (robust max)."""
        return max(self.children, key=lambda ch: ch.visits)


# ── MCTS agent ────────────────────────────────────────────────────────────────

class MCTSAgent:
    """
    Heuristic Shallow MCTS agent for Azul.

    Parameters
    ----------
    player_id   : int         — 0-indexed player this agent controls
    timeout_ms  : int         — search budget in milliseconds (default 1000)
    c           : float       — UCT exploration constant (√2 is standard)
    max_depth   : int         — simulation depth limit (default 6 plies)
    weights     : EvalWeights — static evaluator weights (see EvalWeights)

    Interface (drop-in for RandomAI)
    ---------------------------------
    agent.choose_move(state_copy, result_queue)
    """

    def __init__(self,
                 player_id:  int,
                 timeout_ms: int         = 1000,
                 c:          float       = 1.414,
                 max_depth:  int         = 6,
                 weights:    EvalWeights = None):
        self.player_id  = player_id
        self.timeout_ms = timeout_ms
        self.c          = c
        self.max_depth  = max_depth
        self.weights    = weights or EvalWeights()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_best_move(self,
                      state:      AzulState,
                      timeout_ms: Optional[int] = None) -> Optional[Move]:
        """
        Run MCTS from `state` for `timeout_ms` ms and return the best move.
        Thread-safe — no shared mutable state between calls.
        """
        ms    = timeout_ms if timeout_ms is not None else self.timeout_ms
        moves = state.get_legal_moves()
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        root     = _Node(_fast_clone(state), parent=None, move=None)
        deadline = time.monotonic() + ms / 1000.0

        while time.monotonic() < deadline:
            # Batch 10 before re-checking the clock (amortises syscall overhead)
            for _ in range(10):
                leaf = self._select(root)
                if not leaf.is_terminal:
                    leaf = self._expand(leaf)
                self._backprop(leaf, self._simulate(leaf))

        return root.best_child_robust().move if root.children else random.choice(moves)

    def choose_move(self, state: AzulState, result_queue: queue.Queue):
        """Drop-in for RandomAI.choose_move — called from a background thread."""
        result_queue.put(self.get_best_move(state))

    # ── MCTS phases ───────────────────────────────────────────────────────────

    def _select(self, node: _Node) -> _Node:
        while (not node.is_terminal
               and node.is_fully_expanded
               and node.children):
            node = node.best_child_uct(self.c)
        return node

    def _expand(self, node: _Node) -> _Node:
        if not node.untried_moves:
            return node
        move      = node.untried_moves.pop()
        new_state = _fast_clone(node.state)
        new_state.apply_move_inplace(move)
        child = _Node(new_state, parent=node, move=move)
        node.children.append(child)
        return child

    def _simulate(self, node: _Node) -> List[float]:
        """
        Shallow simulation: apply up to `max_depth` heuristic moves from
        node.state, then call the static evaluator.

        Replaces the old full-game rollout. Key performance gain:
          Old: ~75 moves × 0.026 ms = 1.95 ms/sim  → ~510/sec
          New:   6 moves × 0.026 ms + eval ≈ 0.18 ms/sim  → ~5 000/sec
        """
        state = _fast_clone(node.state)
        for _ in range(self.max_depth):
            if state.game_over:
                break
            moves = state.get_legal_moves()
            if not moves:
                break
            state.apply_move_inplace(_heuristic_pick(state, moves))
        return evaluate_state(state, self.weights)

    def _backprop(self, node: _Node, values: List[float]):
        while node is not None:
            node.visits += 1
            for i, v in enumerate(values):
                node.total_values[i] += v
            node = node.parent

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def pv_string(self, root: _Node, depth: int = 4) -> str:
        """Principal variation string for debugging / logging."""
        from engine import COLORS
        p    = self.player_id
        lines = [f"MCTS  sims={root.visits}  "
                 f"eval={root.total_values[p]/root.visits:.3f}"
                 if root.visits else "MCTS  sims=0"]
        node = root
        for _ in range(depth):
            if not node.children:
                break
            best = node.best_child_robust()
            m    = best.move
            src  = "中心" if m.source == CENTER else f"工厂{m.source + 1}"
            tgt  = "地板" if m.target_row == FLOOR else f"行{m.target_row + 1}"
            wr   = best.total_values[p] / best.visits if best.visits else 0.0
            lines.append(
                f"  {src}→{COLORS[m.color]}→{tgt}"
                f"  (n={best.visits}, v={wr:.3f})"
            )
            node = best
        return "\n".join(lines)


# ── Benchmark ─────────────────────────────────────────────────────────────────

def benchmark(timeout_ms: int = 2000, num_players: int = 2, seed: int = 42):
    """
    Measure and compare old (full rollout) vs new (shallow + eval) performance.
    Run from repo root: python3 -m ai.mcts_agent
    """
    import statistics

    state = AzulState(num_players=num_players, seed=seed)
    agent = MCTSAgent(player_id=0, timeout_ms=timeout_ms)

    print(f"Benchmark: {num_players}-player game, {timeout_ms} ms budget\n")

    # ── Old: full random rollout cost ─────────────────────────────────────────
    times_full = []
    for _ in range(100):
        s = _fast_clone(state)
        t0 = time.monotonic()
        while not s.game_over:
            mvs = s.get_legal_moves()
            if not mvs: break
            s.apply_move_inplace(random.choice(mvs))
        times_full.append(time.monotonic() - t0)
    avg_full = statistics.mean(times_full) * 1000
    print(f"Full rollout:  {avg_full:.2f} ms/sim  "
          f"→ theoretical max ~{1000/avg_full:.0f}/sec")

    # ── New: shallow simulation cost ──────────────────────────────────────────
    times_shallow = []
    for _ in range(500):
        node = _Node(_fast_clone(state), None, None)
        t0   = time.monotonic()
        agent._simulate(node)
        times_shallow.append(time.monotonic() - t0)
    avg_shallow = statistics.mean(times_shallow) * 1000
    print(f"Shallow sim:   {avg_shallow:.2f} ms/sim  "
          f"→ theoretical max ~{1000/avg_shallow:.0f}/sec")
    print(f"Speedup:       {avg_full/avg_shallow:.1f}×\n")

    # ── Actual MCTS throughput ─────────────────────────────────────────────────
    root     = _Node(_fast_clone(state), None, None)
    deadline = time.monotonic() + timeout_ms / 1000.0
    iters    = 0
    while time.monotonic() < deadline:
        for _ in range(10):
            leaf = agent._select(root)
            if not leaf.is_terminal: leaf = agent._expand(leaf)
            agent._backprop(leaf, agent._simulate(leaf))
        iters += 10

    print(f"Actual MCTS:   {iters} iterations in {timeout_ms} ms "
          f"= {iters*1000/timeout_ms:.0f}/sec")
    print()
    print(agent.pv_string(root))


if __name__ == "__main__":
    benchmark()

"""
花砖物语 (Azul) 核心引擎
严格遵照官方手册规则实现

颜色编码: 0=蓝(B) 1=黄(Y) 2=红(R) 3=绿(G) 4=白(W)
棋盘方向: row=行(0-4, 上到下), col=列(0-4, 左到右)
"""

import copy
import random
from collections import namedtuple
from typing import List, Tuple, Optional, Dict

# ── 常量 ──────────────────────────────────────────────────
CENTER       = -1   # source: 中心区
FLOOR        = -1   # target_row: 地板行

NUM_COLORS   = 5
COLORS       = ['蓝', '黄', '红', '绿', '白']
COLOR_CHARS  = ['B',  'Y',  'R',  'G',  'W']

# 墙面颜色布局 WALL_PATTERN[row][col] = color_id
# 每行每列每种颜色各出现一次（对角线排列）
WALL_PATTERN = [
    [0, 1, 2, 3, 4],   # 蓝 黄 红 绿 白
    [4, 0, 1, 2, 3],   # 白 蓝 黄 红 绿
    [3, 4, 0, 1, 2],   # 绿 白 蓝 黄 红
    [2, 3, 4, 0, 1],   # 红 绿 白 蓝 黄
    [1, 2, 3, 4, 0],   # 黄 红 绿 白 蓝
]

# 地板扣分（最多7格）
FLOOR_PENALTIES = [-1, -1, -2, -2, -2, -3, -3]

# 各人数对应工厂数
NUM_FACTORIES = {2: 5, 3: 7, 4: 9}

# 每种颜色瓷砖总数
TILES_PER_COLOR = 20

# 游戏结算加分
BONUS_ROW    = 2   # 完成一横行
BONUS_COL    = 7   # 完成一竖列
BONUS_COLOR  = 10  # 完成一种颜色（5块全上墙）


# ── 数据结构 ──────────────────────────────────────────────
Move = namedtuple('Move', ['source', 'color', 'target_row'])
"""
source:     工厂索引 0..N-1，或 CENTER(-1) 表示中心区
color:      颜色 0-4
target_row: 样式行 0-4，或 FLOOR(-1) 表示直接扔地板
"""


class PlayerBoard:
    """单个玩家的棋盘状态"""

    def __init__(self):
        # 样式行 pattern_lines[row] = [color, count]
        # color=-1 表示该行为空
        self.pattern_lines: List[List] = [[-1, 0] for _ in range(5)]

        # 墙面 wall[row][col] = bool（是否已放砖）
        self.wall: List[List[bool]] = [[False] * 5 for _ in range(5)]

        # 地板行（存储的瓷砖颜色列表，-2表示起始玩家标记）
        self.floor: List[int] = []

        # 得分
        self.score: int = 0

        # 是否持有起始玩家标记
        self.has_first_marker: bool = False

    def pattern_line_color(self, row: int) -> int:
        """返回样式行当前颜色，-1表示空"""
        return self.pattern_lines[row][0]

    def pattern_line_count(self, row: int) -> int:
        """返回样式行当前瓷砖数"""
        return self.pattern_lines[row][1]

    def pattern_line_full(self, row: int) -> bool:
        """样式行是否已满（行i需要i+1块砖）"""
        return self.pattern_lines[row][1] == row + 1

    def wall_col_for(self, row: int, color: int) -> int:
        """返回颜色在该行对应的墙面列"""
        return WALL_PATTERN[row].index(color)

    def wall_has(self, row: int, color: int) -> bool:
        """墙面该行该颜色是否已放砖"""
        col = self.wall_col_for(row, color)
        return self.wall[row][col]

    def can_place_on_row(self, row: int, color: int) -> bool:
        """
        能否将 color 放在样式行 row？
        条件：
          1. 样式行为空，或已有同色砖且未满
          2. 该行对应的墙面位置尚未放砖
        """
        pl_color, pl_count = self.pattern_lines[row]
        row_capacity = row + 1

        # 样式行已满
        if pl_count >= row_capacity:
            return False

        # 颜色不匹配
        if pl_color != -1 and pl_color != color:
            return False

        # 墙面对应位置已有该颜色
        if self.wall_has(row, color):
            return False

        return True

    def add_to_floor(self, tiles: List[int], is_first_marker: bool = False):
        """将瓷砖/起始玩家标记放入地板行"""
        if is_first_marker:
            self.floor.append(-2)  # -2 = 起始玩家标记
            self.has_first_marker = True
        for t in tiles:
            self.floor.append(t)

    def floor_penalty(self) -> int:
        """计算地板扣分"""
        count = min(len(self.floor), len(FLOOR_PENALTIES))
        return sum(FLOOR_PENALTIES[:count])


class AzulState:
    """完整的游戏状态（可拷贝，用于 MCTS 等 AI）"""

    def __init__(self, num_players: int = 2, seed: int = None):
        assert 2 <= num_players <= 4
        self.num_players   = num_players
        self.num_factories = NUM_FACTORIES[num_players]
        self.rng           = random.Random(seed)

        # 玩家棋盘
        self.boards: List[PlayerBoard] = [PlayerBoard() for _ in range(num_players)]

        # 工厂 factories[i] = {color: count}
        self.factories: List[Dict[int, int]] = [{} for _ in range(self.num_factories)]

        # 中心区 center = {color: count}，-2=起始玩家标记
        self.center: Dict[int, int] = {-2: 1}  # 游戏开始时放入起始玩家标记

        # 瓷砖袋 & 丢弃堆
        self.bag:      List[int] = []
        self.discard:  List[int] = []

        # 当前玩家
        self.current_player: int = 0

        # 下一轮起始玩家（谁拿了起始标记）
        self._next_first_player: Optional[int] = None

        # 游戏阶段: 'taking' | 'tiling' | 'end'
        self.phase: str = 'taking'

        # 游戏是否结束
        self.game_over: bool = False

        # 初始化瓷砖袋
        self._init_bag()
        self._fill_factories()

    # ── 初始化 ────────────────────────────────────────────

    def _init_bag(self):
        self.bag = [c for c in range(NUM_COLORS) for _ in range(TILES_PER_COLOR)]
        self.rng.shuffle(self.bag)

    def _draw_tiles(self, n: int) -> List[int]:
        """从袋中取 n 块砖，不足时先从丢弃堆补充"""
        drawn = []
        for _ in range(n):
            if not self.bag:
                if not self.discard:
                    break
                self.bag = self.discard[:]
                self.discard = []
                self.rng.shuffle(self.bag)
            if self.bag:
                drawn.append(self.bag.pop())
        return drawn

    def _fill_factories(self):
        """每轮开始时，向每个工厂放4块砖"""
        for i in range(self.num_factories):
            self.factories[i] = {}
            tiles = self._draw_tiles(4)
            for t in tiles:
                self.factories[i][t] = self.factories[i].get(t, 0) + 1

    # ── 合法移动 ──────────────────────────────────────────

    def get_legal_moves(self) -> List[Move]:
        """返回当前玩家所有合法移动"""
        if self.phase != 'taking':
            return []

        board  = self.boards[self.current_player]
        moves  = []

        # 从工厂取砖
        for fi, factory in enumerate(self.factories):
            for color, count in factory.items():
                if count == 0:
                    continue
                # 可以放入任意合法的样式行，或直接扔地板
                placed = False
                for row in range(5):
                    if board.can_place_on_row(row, color):
                        moves.append(Move(source=fi, color=color, target_row=row))
                        placed = True
                # 总是可以选择扔地板
                moves.append(Move(source=fi, color=color, target_row=FLOOR))

        # 从中心区取砖
        for color, count in self.center.items():
            if color == -2 or count == 0:
                continue
            placed = False
            for row in range(5):
                if board.can_place_on_row(row, color):
                    moves.append(Move(source=CENTER, color=color, target_row=row))
                    placed = True
            moves.append(Move(source=CENTER, color=color, target_row=FLOOR))

        return moves

    # ── 应用移动 ──────────────────────────────────────────

    def apply_move(self, move: Move) -> 'AzulState':
        """
        应用一步移动，返回新状态（不修改原状态）
        move: Move(source, color, target_row)
        """
        s = copy.deepcopy(self)
        s._do_move(move)
        return s

    def apply_move_inplace(self, move: Move):
        """就地修改状态（效率更高，用于正式对局）"""
        self._do_move(move)

    def apply_move_no_tiling(self, move: Move) -> 'AzulState':
        """Apply move to a copy WITHOUT auto-executing tiling phase (for UI animation)"""
        s = copy.deepcopy(self)
        s._do_move(move, execute_tiling=False)
        return s

    def apply_move_inplace_no_tiling(self, move: Move):
        """Apply move in-place WITHOUT auto-executing tiling phase (for UI animation)"""
        self._do_move(move, execute_tiling=False)

    def _do_move(self, move: Move, execute_tiling: bool = True):
        board = self.boards[self.current_player]
        source, color, target_row = move

        # ── 取砖 ──────────────────────────────────────────
        took_first_marker = False

        if source == CENTER:
            count = self.center.get(color, 0)
            assert count > 0, f"中心区没有颜色 {color} 的砖"
            taken = count
            self.center[color] = 0
            # 取走起始玩家标记
            if self.center.get(-2, 0) > 0:
                self.center[-2] = 0
                took_first_marker = True
                # 记录下一轮起始玩家
                self._next_first_player = self.current_player
        else:
            factory = self.factories[source]
            count = factory.get(color, 0)
            assert count > 0, f"工厂 {source} 没有颜色 {color} 的砖"
            taken = count
            factory[color] = 0
            # 剩余砖移入中心
            for c, cnt in factory.items():
                if cnt > 0:
                    self.center[c] = self.center.get(c, 0) + cnt
                    factory[c] = 0

        # ── 放砖 ──────────────────────────────────────────
        if target_row == FLOOR:
            # 全部扔地板
            overflow = [color] * taken
            board.add_to_floor(overflow, took_first_marker)
        else:
            row_capacity = target_row + 1
            current_count = board.pattern_lines[target_row][1]
            space_left = row_capacity - current_count

            # 能放入样式行的数量
            can_place = min(taken, space_left)
            overflow_count = taken - can_place

            # 更新样式行
            board.pattern_lines[target_row][0] = color
            board.pattern_lines[target_row][1] += can_place

            # 溢出扔地板
            overflow = [color] * overflow_count
            board.add_to_floor(overflow, took_first_marker)

        # ── 轮换玩家 ──────────────────────────────────────
        self.current_player = (self.current_player + 1) % self.num_players

        # ── 检查取砖阶段是否结束 ─────────────────────────
        if execute_tiling and self._taking_phase_over():
            self._execute_tiling_phase()

    def _taking_phase_over(self) -> bool:
        """工厂和中心区都没有可取的砖了"""
        for factory in self.factories:
            if any(c > 0 for c in factory.values()):
                return False
        for color, count in self.center.items():
            if color != -2 and count > 0:
                return False
        return True

    # ── 贴砖阶段 ──────────────────────────────────────────

    def _execute_tiling_phase(self):
        """
        轮次结束：
        1. 完整样式行 → 移一块砖到墙面并计分
        2. 地板扣分
        3. 多余砖扔弃砖堆
        4. 检查游戏是否结束
        5. 补充工厂，开始新一轮
        """
        for pid, board in enumerate(self.boards):
            # 处理每一行
            for row in range(5):
                if board.pattern_line_full(row):
                    color = board.pattern_lines[row][0]
                    col   = board.wall_col_for(row, color)

                    # 放砖到墙面
                    board.wall[row][col] = True

                    # 计分（相邻砖）
                    pts = self._score_placement(board, row, col)
                    board.score += pts

                    # 剩余砖（row+1块只保留1块上墙，其余丢弃）
                    discarded = [color] * row   # row=行索引，共row+1块，1块上墙
                    self.discard.extend(discarded)

                    # 清空样式行
                    board.pattern_lines[row] = [-1, 0]

            # 地板扣分
            penalty = board.floor_penalty()
            board.score = max(0, board.score + penalty)

            # 丢弃地板上的砖（-2是标记，其余入弃砖堆）
            for tile in board.floor:
                if tile >= 0:
                    self.discard.append(tile)
            board.floor = []
            board.has_first_marker = False

        # 检查游戏是否结束（有人完成了一横行）
        if self._check_game_over():
            self._final_scoring()
            self.game_over = True
            self.phase = 'end'
            return

        # ── 确定下一轮起始玩家 ────────────────────────────
        # 必须在清空地板之前记录谁拿了起始标记
        # （此处 has_first_marker 已在上方地板清空时重置为 False）
        # 修复：在清空地板前记录 next_first_player
        # 实际已在下方通过 _next_first_player 记录
        if self._next_first_player is not None:
            self.current_player = self._next_first_player
            self._next_first_player = None

        # 补充工厂，开始新一轮
        self.center = {-2: 1}  # 起始玩家标记重入中心
        self._fill_factories()
        self.phase = 'taking'

    def _score_placement(self, board: PlayerBoard, row: int, col: int) -> int:
        """
        计算在 (row, col) 放砖后的得分
        官方规则：
          - 如果周围没有相邻砖：得1分
          - 否则：
            * 统计水平连续段长度（含自身）
            * 统计垂直连续段长度（含自身）
            * 有水平邻居加水平长度分，有垂直邻居加垂直长度分
        """
        h_len = self._count_adjacent(board.wall, row, col, horizontal=True)
        v_len = self._count_adjacent(board.wall, row, col, horizontal=False)

        h_neighbors = h_len > 1
        v_neighbors = v_len > 1

        if not h_neighbors and not v_neighbors:
            return 1

        score = 0
        if h_neighbors:
            score += h_len
        if v_neighbors:
            score += v_len
        return score

    @staticmethod
    def _count_adjacent(wall: List[List[bool]], row: int, col: int,
                        horizontal: bool) -> int:
        """统计从 (row,col) 出发，水平或垂直方向的连续砖数（含自身）"""
        count = 1
        if horizontal:
            # 向左
            c = col - 1
            while c >= 0 and wall[row][c]:
                count += 1; c -= 1
            # 向右
            c = col + 1
            while c < 5 and wall[row][c]:
                count += 1; c += 1
        else:
            # 向上
            r = row - 1
            while r >= 0 and wall[r][col]:
                count += 1; r -= 1
            # 向下
            r = row + 1
            while r < 5 and wall[r][col]:
                count += 1; r += 1
        return count

    # ── 结束判断 ──────────────────────────────────────────

    def _check_game_over(self) -> bool:
        """任意玩家完成至少一整行，游戏结束"""
        for board in self.boards:
            for row in range(5):
                if all(board.wall[row]):
                    return True
        return False

    def _final_scoring(self):
        """游戏结束时的加分项"""
        for board in self.boards:
            # 完整横行 +2
            for row in range(5):
                if all(board.wall[row]):
                    board.score += BONUS_ROW

            # 完整竖列 +7
            for col in range(5):
                if all(board.wall[row][col] for row in range(5)):
                    board.score += BONUS_COL

            # 同色全上墙 +10
            for color in range(NUM_COLORS):
                positions = [(r, WALL_PATTERN[r].index(color)) for r in range(5)]
                if all(board.wall[r][c] for r, c in positions):
                    board.score += BONUS_COLOR

    # ── 逐步得分预览（UI动画用）────────────────────────────

    def preview_tiling(self) -> List[dict]:
        """
        预计算本轮结束时所有贴砖得分事件，不修改状态。
        返回列表，每项：
          {
            'player_id': int,
            'row': int,          # 样式行 / 墙面行
            'col': int,          # 墙面列
            'color': int,
            'pts': int,          # 放砖得分
            'h_tiles': [(r,c)],  # 水平连续砖坐标（含自身）
            'v_tiles': [(r,c)],  # 垂直连续砖坐标（含自身）
            'floor_penalty': int,# 地板扣分（仅每玩家最后一项非0）
            'score_before': int,
            'score_after': int,
          }
        """
        import copy
        sim = copy.deepcopy(self)   # 在副本上模拟
        steps: List[dict] = []

        for pid, board in enumerate(sim.boards):
            floor_pen = board.floor_penalty()

            for row in range(5):
                if not board.pattern_line_full(row):
                    continue

                color = board.pattern_lines[row][0]
                col   = board.wall_col_for(row, color)

                # 放砖（在副本上）
                board.wall[row][col] = True

                # 计算本砖得分明细
                h_tiles = sim._adjacent_tiles(board.wall, row, col, horizontal=True)
                v_tiles = sim._adjacent_tiles(board.wall, row, col, horizontal=False)
                pts     = sim._score_placement(board, row, col)

                score_before = board.score
                board.score  = max(0, board.score + pts)
                score_after  = board.score

                steps.append({
                    'player_id':    pid,
                    'row':          row,
                    'col':          col,
                    'color':        color,
                    'pts':          pts,
                    'h_tiles':      h_tiles,
                    'v_tiles':      v_tiles,
                    'floor_penalty': 0,
                    'score_before': score_before,
                    'score_after':  score_after,
                    'label':        f"+{pts}",
                })

                board.pattern_lines[row] = [-1, 0]

            # 地板扣分事件
            if floor_pen != 0:
                sb = board.score
                board.score = max(0, board.score + floor_pen)
                steps.append({
                    'player_id':    pid,
                    'row':          -1,
                    'col':          -1,
                    'color':        -1,
                    'pts':          floor_pen,
                    'h_tiles':      [],
                    'v_tiles':      [],
                    'floor_penalty': floor_pen,
                    'score_before': sb,
                    'score_after':  board.score,
                    'label':        str(floor_pen),
                })

        return steps

    @staticmethod
    def _adjacent_tiles(wall: List[List[bool]], row: int, col: int,
                        horizontal: bool) -> List[Tuple[int, int]]:
        """返回连续砖坐标列表（含自身）"""
        tiles = [(row, col)]
        if horizontal:
            c = col - 1
            while c >= 0 and wall[row][c]:
                tiles.append((row, c)); c -= 1
            c = col + 1
            while c < 5 and wall[row][c]:
                tiles.append((row, c)); c += 1
        else:
            r = row - 1
            while r >= 0 and wall[r][col]:
                tiles.append((r, col)); r -= 1
            r = row + 1
            while r < 5 and wall[r][col]:
                tiles.append((r, col)); r += 1
        return tiles

    # ── 查询接口 ──────────────────────────────────────────

    def scores(self) -> List[int]:
        return [b.score for b in self.boards]

    def get_final_bonuses(self) -> List[dict]:
        """
        计算每位玩家的结算加分明细（可在 game_over 后随时调用）。
        返回列表，每项：
          {
            'rows':       完成横行数,
            'cols':       完成竖列数,
            'colors':     完成颜色数,
            'row_pts':    横行加分合计,
            'col_pts':    竖列加分合计,
            'color_pts':  颜色加分合计,
            'bonus_total':三项加分之和,
          }
        """
        result = []
        for board in self.boards:
            rows_done = sum(
                1 for r in range(5) if all(board.wall[r])
            )
            cols_done = sum(
                1 for c in range(5)
                if all(board.wall[r][c] for r in range(5))
            )
            colors_done = sum(
                1 for color in range(NUM_COLORS)
                if all(board.wall[r][WALL_PATTERN[r].index(color)]
                       for r in range(5))
            )
            result.append({
                'rows':        rows_done,
                'cols':        cols_done,
                'colors':      colors_done,
                'row_pts':     rows_done   * BONUS_ROW,
                'col_pts':     cols_done   * BONUS_COL,
                'color_pts':   colors_done * BONUS_COLOR,
                'bonus_total': (rows_done  * BONUS_ROW
                                + cols_done  * BONUS_COL
                                + colors_done * BONUS_COLOR),
            })
        return result

    def winner(self) -> Optional[int]:
        """返回得分最高的玩家编号，游戏未结束时返回 None"""
        if not self.game_over:
            return None
        s = self.scores()
        return s.index(max(s))

    def clone(self) -> 'AzulState':
        return copy.deepcopy(self)

    # ── 调试输出 ──────────────────────────────────────────

    def render(self):
        """在终端打印当前棋盘状态"""
        print("=" * 60)
        print(f"  花砖物语 | 阶段: {self.phase} | 当前玩家: P{self.current_player}")
        print("=" * 60)

        # 工厂
        print("\n  【工厂】")
        for i, f in enumerate(self.factories):
            tiles = " ".join(
                COLOR_CHARS[c] * cnt
                for c, cnt in sorted(f.items()) if cnt > 0
            )
            print(f"  工厂{i}: [{tiles or '空'}]")

        # 中心
        center_tiles = " ".join(
            ("★" if c == -2 else COLOR_CHARS[c]) + f"×{cnt}"
            for c, cnt in sorted(self.center.items()) if cnt > 0
        )
        print(f"  中心: [{center_tiles or '空'}]")

        # 玩家棋盘
        for pid, board in enumerate(self.boards):
            marker = "★" if board.has_first_marker else ""
            print(f"\n  ── P{pid} {marker}  得分: {board.score} ──")

            # 样式行 + 墙面
            print("  样式行          墙面")
            for row in range(5):
                # 样式行（右对齐）
                pl_color, pl_count = board.pattern_lines[row]
                capacity = row + 1
                if pl_color == -1:
                    pl_str = "." * capacity
                else:
                    pl_str = "." * (capacity - pl_count) + COLOR_CHARS[pl_color] * pl_count
                pl_display = f"{pl_str:>5}"

                # 墙面
                wall_str = " ".join(
                    COLOR_CHARS[WALL_PATTERN[row][col]] if board.wall[row][col] else "."
                    for col in range(5)
                )
                print(f"  {pl_display}  |  {wall_str}")

            # 地板
            floor_str = " ".join(
                "★" if t == -2 else COLOR_CHARS[t]
                for t in board.floor
            )
            penalty = board.floor_penalty()
            print(f"  地板: [{floor_str}] ({penalty:+d}分)")

        print()

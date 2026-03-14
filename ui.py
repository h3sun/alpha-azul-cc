"""
花砖物语 (Azul) — Pygame UI
支持 MacBook M1 Retina 高清显示
运行: python3 ui.py
依赖: pip install pygame
"""

import os
import sys
import math
import threading
import queue
import time
import pygame

# ── Retina/HiDPI 支持（必须在 pygame.init 之前设置）────────
os.environ["SDL_VIDEO_HIGHDPI"] = "1"
sys.path.insert(0, os.path.dirname(__file__))

from engine import (AzulState, Move, CENTER, FLOOR,
                    WALL_PATTERN, COLOR_CHARS, COLORS, NUM_COLORS)
from ai.mcts_agent import MCTSAgent

# ──────────────────────────────────────────────────────────────
# 颜色常量
# ──────────────────────────────────────────────────────────────
class C:
    BLUE   = (  0, 121, 191)
    YELLOW = (242, 169,   0)
    RED    = (226,  35,  26)
    GREEN  = ( 34, 168,  76)   # 绿色替换黑色
    WHITE  = (230, 230, 230)

    TILE_COLORS = [BLUE, YELLOW, RED, GREEN, WHITE]

    BG          = ( 28,  28,  40)
    PANEL       = ( 40,  40,  58)
    PANEL_DARK  = ( 22,  22,  32)
    BORDER      = ( 80,  80, 110)
    HIGHLIGHT   = (255, 215,   0)
    LEGAL_HINT  = ( 80, 200,  80)
    H_GLOW      = (100, 200, 255)
    V_GLOW      = (100, 255, 150)
    SCORE_POP   = (255, 230,  50)
    SCORE_NEG   = (255,  80,  80)
    FLOOR_PEN   = ( 80,  20,  20)
    TEXT_MAIN   = (235, 235, 245)
    TEXT_DIM    = (130, 130, 160)
    FLOOR_BG    = ( 60,  28,  28)
    MARKER      = (255, 200,  50)
    EMPTY_TILE  = ( 55,  55,  75)
    WALL_EMPTY  = ( 45,  45,  62)

# ──────────────────────────────────────────────────────────────
# 布局常量（逻辑像素，1280×720）
# ──────────────────────────────────────────────────────────────
LW, LH = 1280, 720   # 逻辑分辨率

TILE   = 38          # 瓷砖边长
GAP    =  4          # 瓷砖间距
STEP   = TILE + GAP  # 步长

# 各区域起点
INFO_H      = 52     # 顶部信息栏高度
FACTORY_X   = 18     # 工厂区 X 起点
FACTORY_Y   = INFO_H + 14
CENTER_X    = 18
BOARD_X     = 510    # 玩家棋盘区 X 起点
BOARD_Y     = [INFO_H + 8, INFO_H + 8 + 330]  # P0, P1 的 Y

# 工厂布局（2行，第一行3个，第二行2个）
FACTORY_COLS = 3
FACTORY_W    = 4 * STEP + 16
FACTORY_H    = 4 * STEP + 16

# 玩家棋盘内部偏移
PL_LABEL_H  = 26     # 玩家标签高度
PL_PAD      = 12     # 棋盘内边距
WALL_OFFSET = 5 * STEP + 30  # 墙面相对于棋盘左边


# ──────────────────────────────────────────────────────────────
# 动画系统
# ──────────────────────────────────────────────────────────────
class TileAnim:
    """单块瓷砖飞行动画"""
    def __init__(self, color: int, start, end, duration=0.35):
        self.color    = color
        self.start    = pygame.Vector2(start)
        self.end      = pygame.Vector2(end)
        self.duration = duration
        self.elapsed  = 0.0
        self.done     = False

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.elapsed = self.duration
            self.done = True

    @property
    def pos(self) -> pygame.Vector2:
        t = min(self.elapsed / self.duration, 1.0)
        t = t * t * (3 - 2 * t)          # smoothstep
        return self.start.lerp(self.end, t)


class AnimManager:
    def __init__(self):
        self._anims: list[TileAnim] = []
        self.lock = threading.Lock()

    def add(self, color, start, end, duration=0.35):
        with self.lock:
            self._anims.append(TileAnim(color, start, end, duration))

    def update(self, dt: float):
        with self.lock:
            for a in self._anims:
                a.update(dt)
            self._anims = [a for a in self._anims if not a.done]

    def draw(self, surf):
        with self.lock:
            for a in self._anims:
                pos = a.pos
                draw_tile(surf, a.color, int(pos.x), int(pos.y),
                          TILE, alpha=200)

    @property
    def busy(self) -> bool:
        with self.lock:
            return len(self._anims) > 0


# ──────────────────────────────────────────────────────────────
# 绘制工具函数
# ──────────────────────────────────────────────────────────────
def draw_tile(surf, color_id: int, x: int, y: int, size: int,
              alpha: int = 255, border: bool = True,
              highlight: bool = False, dim: bool = False):
    """绘制一块瓷砖"""
    if color_id < 0:
        return
    base_color = C.TILE_COLORS[color_id]
    if dim:
        base_color = tuple(max(0, c // 3) for c in base_color)

    def _bright(col):
        return tuple(min(255, c + 60) for c in col)

    # 半透明时用 Surface
    if alpha < 255:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(s, (*base_color, alpha), (0, 0, size, size), border_radius=5)
        if border:
            pygame.draw.rect(s, (*_bright(base_color), alpha),
                             (0, 0, size, size), 2, border_radius=5)
        surf.blit(s, (x, y))
    else:
        rect = pygame.Rect(x, y, size, size)
        pygame.draw.rect(surf, base_color, rect, border_radius=5)
        if border:
            pygame.draw.rect(surf, _bright(base_color), rect, 2, border_radius=5)
        if highlight:
            pygame.draw.rect(surf, C.HIGHLIGHT, rect, 3, border_radius=5)


def draw_empty_slot(surf, x: int, y: int, size: int,
                    hint_color=None, wall_color_id: int = -1):
    """绘制空格（可带颜色提示）"""
    rect = pygame.Rect(x, y, size, size)
    bg   = C.WALL_EMPTY if wall_color_id >= 0 else C.EMPTY_TILE
    pygame.draw.rect(surf, bg, rect, border_radius=5)

    if wall_color_id >= 0:
        base = C.TILE_COLORS[wall_color_id]
        dim  = tuple(c // 5 for c in base)
        inner = rect.inflate(-8, -8)
        pygame.draw.rect(surf, dim, inner, border_radius=3)

    if hint_color:
        pygame.draw.rect(surf, hint_color, rect, 2, border_radius=5)


def draw_marker(surf, x: int, y: int, size: int):
    """绘制起始玩家标记（五角星）"""
    cx, cy = x + size // 2, y + size // 2
    r = size // 2 - 3
    pts = []
    for i in range(5):
        a = math.pi / 2 + i * 2 * math.pi / 5
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    inner = r * 0.4
    star  = []
    for i in range(5):
        a1 = math.pi / 2 + i * 2 * math.pi / 5
        a2 = a1 + math.pi / 5
        star.append((cx + r     * math.cos(a1), cy - r     * math.sin(a1)))
        star.append((cx + inner * math.cos(a2), cy - inner * math.sin(a2)))
    pygame.draw.polygon(surf, C.MARKER, star)


def rounded_rect(surf, color, rect, radius=8, border=0, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, border, border_radius=radius)


# ──────────────────────────────────────────────────────────────
# 命中测试：返回 (factory_idx_or_CENTER, color, tile_rect)
# ──────────────────────────────────────────────────────────────
class HitMap:
    """记录所有可点击区域 → (source, color) 或 (PLAYER, row)"""
    def __init__(self):
        self._sources: list[tuple] = []   # (rect, source, color)
        self._targets: list[tuple] = []   # (rect, player_id, row)

    def clear(self):
        self._sources.clear()
        self._targets.clear()

    def add_source(self, rect, source, color):
        self._sources.append((pygame.Rect(rect), source, color))

    def add_target(self, rect, player_id, row):
        self._targets.append((pygame.Rect(rect), player_id, row))

    def hit_source(self, pos):
        for rect, source, color in self._sources:
            if rect.collidepoint(pos):
                return source, color
        return None

    def hit_target(self, pos):
        for rect, player_id, row in self._targets:
            if rect.collidepoint(pos):
                return player_id, row
        return None


# ──────────────────────────────────────────────────────────────
# 主渲染器
# ──────────────────────────────────────────────────────────────
class Renderer:
    def __init__(self, surf: pygame.Surface, fonts: dict):
        self.surf  = surf
        self.fonts = fonts
        self.hitmap = HitMap()

    def render(self, state: AzulState, ui_state: 'UIState', anims: AnimManager):
        self.surf.fill(C.BG)
        self.hitmap.clear()

        self._draw_info_bar(state, ui_state)
        self._draw_factories(state, ui_state)
        self._draw_center(state, ui_state)
        for pid in range(state.num_players):
            self._draw_player_board(state, pid, ui_state)
        self._draw_instructions(ui_state)

        anims.draw(self.surf)

        # 得分阶段覆盖层
        if ui_state.is_scoring:
            self._draw_scoring_overlay(state, ui_state.scoring)
            ui_state.scoring.draw_popups(self.surf, self.fonts['bold'])

        if state.game_over:
            self._draw_game_over(state)

    # ── 顶部信息栏 ────────────────────────────────────────────
    def _draw_info_bar(self, state: AzulState, ui_state: 'UIState'):
        bar_rect = pygame.Rect(0, 0, LW, INFO_H)
        rounded_rect(self.surf, C.PANEL_DARK, bar_rect)
        pygame.draw.line(self.surf, C.BORDER, (0, INFO_H), (LW, INFO_H), 1)

        # 标题
        title = self.fonts['title'].render("🀄 花砖物语 Azul", True, C.TEXT_MAIN)
        self.surf.blit(title, (16, 10))

        # 当前玩家
        cp = state.current_player
        txt = f"当前行动: 玩家 {cp + 1}"
        color = C.HIGHLIGHT if not state.game_over else C.TEXT_DIM
        t = self.fonts['normal'].render(txt, True, color)
        self.surf.blit(t, (LW // 2 - t.get_width() // 2, 14))

        # 分数
        for pid in range(state.num_players):
            score = state.boards[pid].score
            marker = "★ " if state.boards[pid].has_first_marker else ""
            txt = f"P{pid+1}: {marker}{score}分"
            col = C.HIGHLIGHT if pid == cp else C.TEXT_DIM
            t   = self.fonts['normal'].render(txt, True, col)
            x   = LW - 280 + pid * 140
            self.surf.blit(t, (x, 14))

    # ── 工厂区 ────────────────────────────────────────────────
    def _draw_factories(self, state: AzulState, ui_state: 'UIState'):
        legal_sources = set()
        if ui_state.selected_source is None:
            for m in state.get_legal_moves():
                legal_sources.add((m.source, m.color))

        n = state.num_factories
        cols = 3
        for fi in range(n):
            row_i = fi // cols
            col_i = fi % cols
            fx = FACTORY_X + col_i * (FACTORY_W + 10)
            fy = FACTORY_Y + row_i * (FACTORY_H + 10)

            # 工厂背景
            frect = pygame.Rect(fx - 6, fy - 6, FACTORY_W + 12, FACTORY_H + 12)
            rounded_rect(self.surf, C.PANEL, frect, radius=10,
                         border=1, border_color=C.BORDER)

            label = self.fonts['small'].render(f"工厂 {fi+1}", True, C.TEXT_DIM)
            self.surf.blit(label, (fx - 2, fy - 24))

            # 绘制4格，每格最多1种颜色
            factory = state.factories[fi]
            tile_list = []
            for c, cnt in factory.items():
                tile_list.extend([c] * cnt)

            for slot in range(4):
                tx = fx + (slot % 2) * STEP
                ty = fy + (slot // 2) * STEP
                if slot < len(tile_list):
                    color_id = tile_list[slot]
                    is_sel  = (ui_state.selected_source == (fi, color_id))
                    is_hint = (fi, color_id) in legal_sources
                    draw_tile(self.surf, color_id, tx, ty, TILE,
                              highlight=is_sel)
                    if is_hint and not is_sel:
                        pygame.draw.rect(self.surf, C.LEGAL_HINT,
                                        (tx, ty, TILE, TILE), 2, border_radius=5)
                    self.hitmap.add_source((tx, ty, TILE, TILE), fi, color_id)
                else:
                    draw_empty_slot(self.surf, tx, ty, TILE)

    # ── 中心区 ────────────────────────────────────────────────
    def _draw_center(self, state: AzulState, ui_state: 'UIState'):
        cy_start = FACTORY_Y + 2 * (FACTORY_H + 10) + 10
        cx_label = self.fonts['small'].render("中心区", True, C.TEXT_DIM)
        self.surf.blit(cx_label, (CENTER_X, cy_start - 22))

        # 背景
        max_tiles = 30
        cols = 8
        rows = math.ceil(max_tiles / cols)
        crect = pygame.Rect(CENTER_X - 6, cy_start - 6,
                            cols * STEP + 12, rows * STEP + 12)
        rounded_rect(self.surf, C.PANEL, crect, radius=10,
                     border=1, border_color=C.BORDER)

        legal_sources = set()
        if ui_state.selected_source is None:
            for m in state.get_legal_moves():
                if m.source == CENTER:
                    legal_sources.add(m.color)

        slot = 0
        # 起始玩家标记
        if state.center.get(-2, 0) > 0:
            tx = CENTER_X + (slot % cols) * STEP
            ty = cy_start + (slot // cols) * STEP
            draw_marker(self.surf, tx, ty, TILE)
            slot += 1

        for color_id in range(NUM_COLORS):
            cnt = state.center.get(color_id, 0)
            for _ in range(cnt):
                tx = CENTER_X + (slot % cols) * STEP
                ty = cy_start + (slot // cols) * STEP
                is_sel  = (ui_state.selected_source == (CENTER, color_id))
                is_hint = color_id in legal_sources
                draw_tile(self.surf, color_id, tx, ty, TILE, highlight=is_sel)
                if is_hint and not is_sel:
                    pygame.draw.rect(self.surf, C.LEGAL_HINT,
                                    (tx, ty, TILE, TILE), 2, border_radius=5)
                self.hitmap.add_source((tx, ty, TILE, TILE), CENTER, color_id)
                slot += 1

    # ── 玩家棋盘 ──────────────────────────────────────────────
    def _draw_player_board(self, state: AzulState, pid: int,
                           ui_state: 'UIState'):
        board = state.boards[pid]
        bx    = BOARD_X
        by    = BOARD_Y[pid]
        bw    = LW - BOARD_X - 10
        bh    = 318

        # 棋盘背景
        brect = pygame.Rect(bx, by, bw, bh)
        bg    = C.PANEL if pid == state.current_player else C.PANEL_DARK
        rounded_rect(self.surf, bg, brect, radius=10,
                     border=2,
                     border_color=(C.HIGHLIGHT
                                   if pid == state.current_player
                                   else C.BORDER))

        # 玩家标签
        marker_str = " ★" if board.has_first_marker else ""
        label = self.fonts['bold'].render(
            f"玩家 {pid+1}{marker_str}    {board.score} 分", True,
            C.HIGHLIGHT if pid == state.current_player else C.TEXT_MAIN)
        self.surf.blit(label, (bx + PL_PAD, by + 8))

        content_y = by + PL_LABEL_H + PL_PAD

        # 计算合法目标行（仅当前玩家且已选source）
        legal_rows = set()
        if (ui_state.selected_source is not None and
                pid == state.current_player):
            src, col = ui_state.selected_source
            for m in state.get_legal_moves():
                if m.source == src and m.color == col:
                    if m.target_row != FLOOR:
                        legal_rows.add(m.target_row)

        # 样式行（右对齐，紧贴墙面左侧）
        wall_x = bx + PL_PAD + 5 * STEP + 30   # 墙面起点
        pl_right = wall_x - 16                   # 样式行右边界

        for row in range(5):
            capacity = row + 1
            pl_color, pl_count = board.pattern_lines[row]
            ry = content_y + row * STEP

            is_legal = row in legal_rows
            if is_legal and ui_state.selected_source is not None:
                sel_color = ui_state.selected_source[1]
                hint_col  = C.TILE_COLORS[sel_color]
            else:
                hint_col  = None

            # 样式行格子（从右向左填）
            for slot in range(capacity):
                # 从右向左摆放格子
                tx = pl_right - (slot + 1) * STEP + GAP
                ty = ry

                filled = slot < pl_count
                if filled:
                    hl = (is_legal and
                          ui_state.selected_source is not None)
                    draw_tile(self.surf, pl_color, tx, ty, TILE,
                              highlight=hl)
                else:
                    draw_empty_slot(self.surf, tx, ty, TILE,
                                    hint_color=hint_col)

            # 整行点击区域
            row_rect = (pl_right - capacity * STEP + GAP,
                        ry, capacity * STEP, TILE)
            self.hitmap.add_target(row_rect, pid, row)

        # 得分动画期间已落定但尚未写入 wall 的砖块
        scoring_placed = set()
        if ui_state.is_scoring:
            for s in ui_state.scoring.placed_tiles:
                if s['player_id'] == pid:
                    scoring_placed.add((s['row'], s['col']))

        # 墙面
        for row in range(5):
            for col in range(5):
                wx = wall_x + col * STEP
                wy = content_y + row * STEP
                wc = WALL_PATTERN[row][col]
                if board.wall[row][col] or (row, col) in scoring_placed:
                    draw_tile(self.surf, wc, wx, wy, TILE)
                else:
                    draw_empty_slot(self.surf, wx, wy, TILE,
                                    wall_color_id=wc)

        # 地板行
        floor_y = content_y + 5 * STEP + 10
        fl_label = self.fonts['small'].render("地板:", True, C.TEXT_DIM)
        self.surf.blit(fl_label, (bx + PL_PAD, floor_y + 4))

        fl_bg = pygame.Rect(bx + PL_PAD + 46, floor_y - 2,
                            7 * STEP + 4, TILE + 4)
        rounded_rect(self.surf, C.FLOOR_BG, fl_bg, radius=5)

        # 地板扣分标注
        penalties = [-1, -1, -2, -2, -2, -3, -3]
        for slot in range(7):
            fx_slot = bx + PL_PAD + 50 + slot * STEP
            fy_slot = floor_y

            # 扣分标注
            p_text = self.fonts['tiny'].render(
                str(penalties[slot]), True, C.TEXT_DIM)
            self.surf.blit(p_text,
                           (fx_slot + TILE // 2 - p_text.get_width() // 2,
                            fy_slot - 14))

            if slot < len(board.floor):
                t = board.floor[slot]
                if t == -2:
                    draw_marker(self.surf, fx_slot, fy_slot, TILE)
                elif t >= 0:
                    draw_tile(self.surf, t, fx_slot, fy_slot, TILE)
            else:
                draw_empty_slot(self.surf, fx_slot, fy_slot, TILE)

        # 地板总扣分
        pen = board.floor_penalty()
        pen_t = self.fonts['small'].render(f"{pen:+d}分", True,
                                           (220, 80, 80) if pen < 0 else C.TEXT_DIM)
        self.surf.blit(pen_t, (bx + PL_PAD + 50 + 7 * STEP + 6, floor_y + 4))

        # 地板点击区域（扔地板）
        floor_rect = (bx + PL_PAD + 50, floor_y, 7 * STEP, TILE)
        self.hitmap.add_target(floor_rect, pid, FLOOR)

    # ── 底部操作提示 ──────────────────────────────────────────
    def _draw_instructions(self, ui_state: 'UIState'):
        if ui_state.selected_source is None:
            msg = "点击工厂或中心区的瓷砖来选取"
        else:
            src, col = ui_state.selected_source
            src_str  = "中心区" if src == CENTER else f"工厂{src+1}"
            color_str = COLORS[col]
            msg = f"已选: {src_str} → {color_str}砖  |  点击样式行放置，或点击地板区直接丢弃"
        t = self.fonts['small'].render(msg, True, C.TEXT_DIM)
        self.surf.blit(t, (LW // 2 - t.get_width() // 2, LH - 22))

    # ── 得分动画覆盖层 ────────────────────────────────────────
    def _draw_scoring_overlay(self, state: AzulState, scoring: 'ScoringPhase'):
        step = scoring.current_step()
        if step is None:
            return

        pid         = step['player_id']
        pts         = step['pts']
        is_floor    = step['floor_penalty'] != 0
        is_positive = pts > 0

        # ── 右侧得分面板 ──────────────────────────────────
        px, py = LW - 260, INFO_H + 10
        pw, ph = 248, 210
        panel  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((20, 20, 35, 210))
        pygame.draw.rect(panel, C.BORDER, (0, 0, pw, ph), 2, border_radius=10)
        self.surf.blit(panel, (px, py))

        # 标题
        if is_floor:
            title = f"P{pid+1} 地板扣分"
        else:
            row, col = step['row'], step['col']
            color_name = COLORS[step['color']]
            title = f"P{pid+1} 第{row+1}行 {color_name}砖"
        t = self.fonts['small'].render(title, True, C.TEXT_DIM)
        self.surf.blit(t, (px + 10, py + 10))

        # 大号得分数字
        label = step['label']
        big_color = C.SCORE_POP if is_positive else C.SCORE_NEG
        big = self.fonts['title'].render(label, True, big_color)
        self.surf.blit(big, (px + pw // 2 - big.get_width() // 2, py + 36))

        # 分数变化
        sb = step['score_before']
        sa = step['score_after']
        change = self.fonts['small'].render(
            f"{sb} → {sa} 分", True, C.TEXT_MAIN)
        self.surf.blit(change, (px + pw // 2 - change.get_width() // 2, py + 90))

        # 得分说明
        if not is_floor and not is_positive:
            pass
        elif not is_floor:
            h_len = len(step['h_tiles'])
            v_len = len(step['v_tiles'])
            y_off = py + 118
            if h_len > 1:
                hl = self.fonts['tiny'].render(
                    f"水平连接 {h_len} 块  +{h_len}", True, C.H_GLOW)
                self.surf.blit(hl, (px + 10, y_off)); y_off += 22
            if v_len > 1:
                vl = self.fonts['tiny'].render(
                    f"垂直连接 {v_len} 块  +{v_len}", True, C.V_GLOW)
                self.surf.blit(vl, (px + 10, y_off)); y_off += 22
            if h_len == 1 and v_len == 1:
                iso = self.fonts['tiny'].render("孤立砖  +1", True, C.TEXT_DIM)
                self.surf.blit(iso, (px + 10, y_off))
        else:
            fl_text = self.fonts['tiny'].render(
                f"地板 {len(state.boards[pid].floor)} 块  {pts:+d}分",
                True, C.SCORE_NEG)
            self.surf.blit(fl_text, (px + 10, py + 118))

        # 进度指示
        total = len(scoring.steps)
        cur   = scoring.current_idx + 1
        prog  = self.fonts['tiny'].render(
            f"步骤 {cur}/{total}", True, C.TEXT_DIM)
        self.surf.blit(prog, (px + pw - prog.get_width() - 10, py + ph - 22))

        # 按空格跳过提示
        skip = self.fonts['tiny'].render("空格 跳过动画", True, C.TEXT_DIM)
        self.surf.blit(skip, (px + 10, py + ph - 22))

        # ── 在墙面上高亮连续砖 ───────────────────────────
        if not is_floor:
            self._highlight_wall_tiles(pid, scoring.h_tiles,
                                       scoring.v_tiles, step['row'], step['col'])

    def _highlight_wall_tiles(self, pid: int,
                               h_tiles: list, v_tiles: list,
                               placed_row: int, placed_col: int):
        """在玩家墙面高亮连续砖"""
        bx = BOARD_X + PL_PAD
        by = BOARD_Y[pid] + PL_LABEL_H + PL_PAD
        wall_x = bx + 5 * STEP + 30

        # 脉冲效果
        pulse = abs(math.sin(time.time() * 4)) * 0.5 + 0.5

        all_h = set(map(tuple, h_tiles))
        all_v = set(map(tuple, v_tiles))

        for (r, c) in all_h:
            wx = wall_x + c * STEP
            wy = by + r * STEP
            s  = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            alpha = int(120 * pulse)
            pygame.draw.rect(s, (*C.H_GLOW, alpha), (0, 0, TILE, TILE),
                             border_radius=5)
            self.surf.blit(s, (wx, wy))
            pygame.draw.rect(self.surf, C.H_GLOW, (wx, wy, TILE, TILE),
                             2, border_radius=5)

        for (r, c) in all_v:
            if (r, c) in all_h:
                continue   # 已画过，不重复
            wx = wall_x + c * STEP
            wy = by + r * STEP
            s  = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            alpha = int(120 * pulse)
            pygame.draw.rect(s, (*C.V_GLOW, alpha), (0, 0, TILE, TILE),
                             border_radius=5)
            self.surf.blit(s, (wx, wy))
            pygame.draw.rect(self.surf, C.V_GLOW, (wx, wy, TILE, TILE),
                             2, border_radius=5)

        # 刚放的砖加强边框
        wx = wall_x + placed_col * STEP
        wy = by + placed_row * STEP
        pygame.draw.rect(self.surf, C.HIGHLIGHT,
                         (wx - 2, wy - 2, TILE + 4, TILE + 4),
                         3, border_radius=6)

    # ── 游戏结束画面 ──────────────────────────────────────────
    def _draw_game_over(self, state: AzulState):
        overlay = pygame.Surface((LW, LH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 175))
        self.surf.blit(overlay, (0, 0))

        winner  = state.winner()
        bonuses = state.get_final_bonuses()
        n       = state.num_players

        # ── 面板尺寸 ──────────────────────────────────────
        PW  = min(820, LW - 60)
        ROW_H = 84          # 每个玩家占的高度
        HDR_H = 80          # 标题区高度
        FTR_H = 40          # 底部提示高度
        PH  = HDR_H + n * ROW_H + 16 + FTR_H
        px  = LW // 2 - PW // 2
        py  = LH // 2 - PH // 2

        # 面板背景
        panel = pygame.Surface((PW, PH), pygame.SRCALPHA)
        panel.fill((18, 18, 30, 230))
        pygame.draw.rect(panel, C.BORDER, (0, 0, PW, PH), 2, border_radius=14)
        self.surf.blit(panel, (px, py))

        # ── 标题 ──────────────────────────────────────────
        t = self.fonts['title'].render("游戏结束！", True, C.TEXT_MAIN)
        self.surf.blit(t, (LW // 2 - t.get_width() // 2, py + 10))

        win_txt = f"🏆  玩家 {winner + 1} 获胜！"
        t = self.fonts['title'].render(win_txt, True, C.HIGHLIGHT)
        self.surf.blit(t, (LW // 2 - t.get_width() // 2, py + 42))

        # ── 每位玩家结算行 ────────────────────────────────
        for pid, (board, bns) in enumerate(zip(state.boards, bonuses)):
            ry      = py + HDR_H + pid * ROW_H
            is_win  = (pid == winner)
            row_col = C.HIGHLIGHT if is_win else C.TEXT_MAIN

            # 行背景
            row_bg = pygame.Surface((PW - 4, ROW_H - 6), pygame.SRCALPHA)
            row_bg.fill((255, 215, 0, 18) if is_win else (60, 60, 80, 80))
            pygame.draw.rect(row_bg, (C.HIGHLIGHT if is_win else C.BORDER),
                             (0, 0, PW - 4, ROW_H - 6), 1, border_radius=8)
            self.surf.blit(row_bg, (px + 2, ry + 2))

            base_score = board.score - bns['bonus_total']

            # 玩家名 + 总分
            name = self.fonts['bold'].render(
                f"玩家 {pid + 1}{'  ★' if is_win else ''}", True, row_col)
            self.surf.blit(name, (px + 18, ry + 10))

            total_t = self.fonts['title'].render(
                f"{board.score} 分", True, row_col)
            self.surf.blit(total_t, (px + PW - total_t.get_width() - 18, ry + 8))

            # ── 明细：游戏得分 + 三项加分 ─────────────────
            segments = [
                (f"游戏 {base_score}", C.TEXT_DIM),
            ]
            if bns['row_pts']:
                segments.append(
                    (f"横行×{bns['rows']} +{bns['row_pts']}", C.H_GLOW))
            if bns['col_pts']:
                segments.append(
                    (f"竖列×{bns['cols']} +{bns['col_pts']}", C.V_GLOW))
            if bns['color_pts']:
                segments.append(
                    (f"颜色×{bns['colors']} +{bns['color_pts']}", C.SCORE_POP))

            dx = px + 18
            for seg_txt, seg_col in segments:
                seg = self.fonts['small'].render(seg_txt, True, seg_col)
                self.surf.blit(seg, (dx, ry + 50))
                dx += seg.get_width() + 18
                # 分隔符
                if seg_txt != segments[-1][0]:
                    sep = self.fonts['small'].render("│", True, C.BORDER)
                    self.surf.blit(sep, (dx - 12, ry + 50))

        # ── 底部提示 ──────────────────────────────────────
        hint = self.fonts['small'].render(
            "按 R 重新开始  /  按 Q 退出", True, C.TEXT_DIM)
        self.surf.blit(hint, (LW // 2 - hint.get_width() // 2,
                               py + PH - FTR_H + 10))


# ──────────────────────────────────────────────────────────────
# 浮动得分文字（"+3" 向上飘然后消失）
# ──────────────────────────────────────────────────────────────
class ScorePopup:
    DURATION = 1.6

    def __init__(self, text: str, x: int, y: int, positive: bool = True):
        self.text     = text
        self.x        = x
        self.y        = float(y)
        self.positive = positive
        self.elapsed  = 0.0
        self.done     = False

    def update(self, dt: float):
        self.elapsed += dt
        self.y       -= 40 * dt    # 向上漂移
        if self.elapsed >= self.DURATION:
            self.done = True

    def draw(self, surf, font):
        t   = min(self.elapsed / self.DURATION, 1.0)
        alpha = int(255 * (1 - t ** 2))
        col = C.SCORE_POP if self.positive else C.SCORE_NEG
        txt = font.render(self.text, True, col)
        s   = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        s.blit(txt, (0, 0))
        s.set_alpha(alpha)
        surf.blit(s, (self.x - txt.get_width() // 2, int(self.y)))


# ──────────────────────────────────────────────────────────────
# 得分步骤控制器（逐步展示贴砖得分）
# ──────────────────────────────────────────────────────────────
class ScoringPhase:
    STEP_DURATION = 1.2   # 每步停留时长（秒）

    def __init__(self, steps: list):
        self.steps        = steps
        self.current_idx  = -1
        self.elapsed      = 0.0
        self.done         = False
        self.popups: list[ScorePopup] = []
        # 当前高亮砖坐标
        self.h_tiles: list = []
        self.v_tiles: list = []
        self.active_player = -1
        self.active_row    = -1
        self.active_col    = -1
        # 已完成步骤中落定到墙面的砖块（用于在动画期间提前显示）
        self.placed_tiles: list[dict] = []
        self._advance()

    def _advance(self):
        # 将刚完成的步骤（若是贴砖而非地板扣分）锁定到墙面
        if self.current_idx >= 0 and self.current_idx < len(self.steps):
            step = self.steps[self.current_idx]
            if step['row'] >= 0:   # 排除地板扣分步骤
                self.placed_tiles.append(step)
        self.current_idx += 1
        self.elapsed       = 0.0
        self.h_tiles       = []
        self.v_tiles       = []
        if self.current_idx >= len(self.steps):
            self.done = True
            return
        step = self.steps[self.current_idx]
        self.active_player = step['player_id']
        self.active_row    = step['row']
        self.active_col    = step['col']
        self.h_tiles       = step['h_tiles']
        self.v_tiles       = step['v_tiles']

    def current_step(self):
        if self.current_idx < len(self.steps):
            return self.steps[self.current_idx]
        return None

    def update(self, dt: float):
        if self.done:
            return
        self.elapsed += dt
        for p in self.popups:
            p.update(dt)
        self.popups = [p for p in self.popups if not p.done]
        if self.elapsed >= self.STEP_DURATION:
            self._advance()

    def spawn_popup(self, text: str, x: int, y: int, positive: bool):
        self.popups.append(ScorePopup(text, x, y, positive))

    def draw_popups(self, surf, font):
        for p in self.popups:
            p.draw(surf, font)


# ──────────────────────────────────────────────────────────────
# UI 状态机
# ──────────────────────────────────────────────────────────────
class UIState:
    def __init__(self):
        self.selected_source  = None   # (source, color) 或 None
        self.ai_thinking      = False
        self.message          = ""
        self.scoring: ScoringPhase | None = None  # 得分动画阶段

    def reset(self):
        self.selected_source = None
        self.ai_thinking     = False

    @property
    def is_scoring(self) -> bool:
        return self.scoring is not None and not self.scoring.done


# ──────────────────────────────────────────────────────────────
# AI — MCTS agent (drop-in replacement for the old RandomAI)
# ──────────────────────────────────────────────────────────────
# MCTSAgent is imported from ai.mcts_agent above.
# Kept here only as a thin fallback for testing without the ai/ module.
class RandomAI:
    """Pure-random fallback; not used when MCTSAgent is available."""
    def __init__(self, player_id: int, delay: float = 0.3):
        self.player_id = player_id
        self.delay     = delay

    def choose_move(self, state: AzulState, result_queue: queue.Queue):
        import random, time
        time.sleep(self.delay)
        moves = state.get_legal_moves()
        result_queue.put(random.choice(moves) if moves else None)


# ──────────────────────────────────────────────────────────────
# 主游戏循环
# ──────────────────────────────────────────────────────────────
class AzulGame:
    def __init__(self, num_players: int = 2, ai_players: set = None):
        pygame.init()
        pygame.display.set_caption("花砖物语 Azul")

        # Retina 处理：先创建逻辑尺寸窗口，再检查实际尺寸
        flags = pygame.SCALED | pygame.RESIZABLE
        self.screen = pygame.display.set_mode((LW, LH), flags)
        self.clock  = pygame.time.Clock()

        # 字体（支持中文需要系统字体）
        self.fonts  = self._load_fonts()

        self.state     = AzulState(num_players=num_players, seed=None)
        self.ui        = UIState()
        self.anims     = AnimManager()
        self.renderer  = Renderer(self.screen, self.fonts)

        # AI 设置：ai_players = {1} 表示玩家1由AI控制（0-indexed）
        self.ai_players  = ai_players or set()
        self.ai_queue    = queue.Queue()
        self.ai_thread   = None

        # 为每个 AI 玩家创建独立的 MCTSAgent（1000 ms 搜索预算）
        self.ai_agents: dict[int, MCTSAgent] = {
            pid: MCTSAgent(player_id=pid, timeout_ms=1000)
            for pid in self.ai_players
        }

    def _load_fonts(self) -> dict:
        """加载字体，优先使用系统中文字体"""
        import pygame.font as pf
        candidates = ["PingFang SC", "Heiti SC", "STHeiti",
                      "Hiragino Sans GB", "WenQuanYi Micro Hei",
                      "Microsoft YaHei", "SimHei"]
        chosen = None
        available = {f.lower() for f in pf.get_fonts()}
        for name in candidates:
            if name.lower() in available or name.lower().replace(" ", "") in available:
                chosen = name
                break

        def make(size, bold=False):
            if chosen:
                try:
                    return pf.SysFont(chosen, size, bold=bold)
                except Exception:
                    pass
            return pf.Font(None, size)

        return {
            'title':  make(28, bold=True),
            'bold':   make(22, bold=True),
            'normal': make(20),
            'small':  make(17),
            'tiny':   make(13),
        }

    def _trigger_ai(self):
        """如果当前玩家是AI，启动后台线程执行 MCTS 搜索"""
        cp = self.state.current_player
        if (cp in self.ai_players and
                not self.state.game_over and
                self.ai_thread is None):
            self.ui.ai_thinking = True
            agent      = self.ai_agents[cp]
            state_copy = self.state.clone()
            self.ai_thread = threading.Thread(
                target=agent.choose_move,
                args=(state_copy, self.ai_queue),
                daemon=True
            )
            self.ai_thread.start()

    def _poll_ai(self):
        """检查AI是否已出招"""
        if self.ai_thread and not self.ai_thread.is_alive():
            self.ai_thread = None
            try:
                move = self.ai_queue.get_nowait()
                if move:
                    # 应用移动（不自动执行贴砖）
                    self.state.apply_move_inplace_no_tiling(move)
                    self.ui.ai_thinking = False
                    if self.state._taking_phase_over():
                        # AI触发了本轮结束 → 启动得分动画
                        self._start_scoring_phase()
                    else:
                        self._trigger_ai()
                else:
                    self.ui.ai_thinking = False
            except queue.Empty:
                pass

    def _start_scoring_phase(self):
        """在贴砖前启动得分动画"""
        steps = self.state.preview_tiling()
        if steps:
            self.ui.scoring = ScoringPhase(steps)
            # 补全第一步的弹出文字（_poll_scoring 只在步骤推进时生成，第0步需手动触发）
            step = self.ui.scoring.current_step()
            if step:
                pid = step['player_id']
                self.ui.scoring.spawn_popup(
                    step['label'],
                    LW - 130,
                    BOARD_Y[pid] + 60,
                    step['pts'] > 0
                )
        else:
            # 没有得分步骤（罕见），直接执行贴砖
            self.state._execute_tiling_phase()
            self._trigger_ai()

    def _poll_scoring(self, dt: float):
        """更新得分动画；动画结束后执行真正的贴砖"""
        if not self.ui.is_scoring:
            return
        sc = self.ui.scoring
        prev_idx = sc.current_idx
        sc.update(dt)

        # 步骤推进时，为新步骤生成弹出文字
        if sc.current_idx != prev_idx and not sc.done:
            step = sc.current_step()
            if step:
                pid = step['player_id']
                sc.spawn_popup(
                    step['label'],
                    LW - 130,
                    BOARD_Y[pid] + 60,
                    step['pts'] > 0
                )

        # 动画自然结束 → 执行真正贴砖（空格跳过走另一路径，此处不会进入）
        if sc.done:
            self.ui.scoring = None
            self.state._execute_tiling_phase()
            self._trigger_ai()

    def _handle_click(self, pos):
        if self.state.game_over or self.ui.ai_thinking or self.anims.busy:
            return
        # 得分动画期间按空格跳过
        if self.ui.is_scoring:
            return

        cp = self.state.current_player
        if cp in self.ai_players:
            return   # 不处理AI玩家的点击

        # 点击1: 选择来源
        if self.ui.selected_source is None:
            hit = self.renderer.hitmap.hit_source(pos)
            if hit:
                source, color = hit
                # 验证：该来源颜色是否有合法移动
                legal = self.state.get_legal_moves()
                valid = any(m.source == source and m.color == color
                            for m in legal)
                if valid:
                    self.ui.selected_source = (source, color)
            return

        # 点击2: 选择目标行（或地板）
        src, col = self.ui.selected_source

        # 先检查是否点击了目标行
        hit_target = self.renderer.hitmap.hit_target(pos)
        if hit_target:
            pid, row = hit_target
            if pid == cp:
                # 验证这个移动是否合法
                legal = self.state.get_legal_moves()
                move  = Move(source=src, color=col, target_row=row)
                if move in legal:
                    # 应用移动（不自动执行贴砖），再判断是否进入贴砖阶段
                    self.state.apply_move_inplace_no_tiling(move)
                    self.ui.reset()
                    if self.state._taking_phase_over():
                        # 触发贴砖：启动得分动画，动画结束后再执行
                        self._start_scoring_phase()
                    else:
                        self._trigger_ai()
                    return

        # 点击了新的来源 → 切换选择
        hit_src = self.renderer.hitmap.hit_source(pos)
        if hit_src:
            source2, color2 = hit_src
            legal = self.state.get_legal_moves()
            valid = any(m.source == source2 and m.color == color2
                        for m in legal)
            if valid:
                self.ui.selected_source = (source2, color2)
                return

        # 点击空白 → 取消选择
        self.ui.selected_source = None

    def run(self):
        self._trigger_ai()
        running = True
        prev_t  = time.time()

        while running:
            now = time.time()
            dt  = now - prev_t
            prev_t = now

            # 事件处理
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_r:
                        self.state = AzulState(
                            num_players=self.state.num_players)
                        self.ui.reset()
                        self.ai_thread = None
                        self.ai_agents = {
                            pid: MCTSAgent(player_id=pid, timeout_ms=1000)
                            for pid in self.ai_players
                        }
                        self._trigger_ai()
                    elif event.key == pygame.K_ESCAPE:
                        self.ui.selected_source = None
                    elif event.key == pygame.K_SPACE:
                        # 空格跳过得分动画
                        if self.ui.is_scoring:
                            self.ui.scoring = None
                            self.state._execute_tiling_phase()
                            self._trigger_ai()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self._handle_click(event.pos)

            # 轮询 AI
            self._poll_ai()

            # 更新得分动画
            self._poll_scoring(dt)

            # 更新动画
            self.anims.update(dt)

            # 渲染
            self.renderer.render(self.state, self.ui, self.anims)

            # AI 思考中提示
            if self.ui.ai_thinking:
                dots = "." * (int(time.time() * 2) % 4)
                t = self.fonts['normal'].render(
                    f"MCTS 思考中{dots}", True, C.YELLOW)
                self.screen.blit(t, (LW // 2 - t.get_width() // 2, LH - 46))

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


# ──────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="花砖物语 Azul")
    parser.add_argument("--players", type=int, default=2,
                        help="玩家数量 (2-4)")
    parser.add_argument("--ai", type=int, nargs="*", default=[],
                        help="AI控制的玩家编号 (0-indexed), 如 --ai 1")
    args = parser.parse_args()

    game = AzulGame(
        num_players=args.players,
        ai_players=set(args.ai)
    )
    game.run()

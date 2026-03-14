#!/usr/bin/env python3
"""
花砖物语引擎测试
"""
import sys
sys.path.insert(0, ".")
from engine import AzulState, Move, CENTER, FLOOR, WALL_PATTERN, COLOR_CHARS

def test_basic():
    print("━" * 50)
    print("  测试1: 基础初始化")
    s = AzulState(num_players=2, seed=42)
    assert len(s.factories) == 5
    assert len(s.boards) == 2
    assert sum(s.bag) >= 0
    assert s.center.get(-2, 0) == 1  # 起始标记在中心
    print("  ✅ 初始化正确")

def test_legal_moves():
    print("\n  测试2: 合法移动生成")
    s = AzulState(num_players=2, seed=42)
    moves = s.get_legal_moves()
    assert len(moves) > 0
    # 每个移动的颜色必须在对应来源中存在
    for m in moves:
        if m.source == CENTER:
            assert s.center.get(m.color, 0) > 0 or m.color == -2
        else:
            assert s.factories[m.source].get(m.color, 0) > 0
    print(f"  ✅ 生成了 {len(moves)} 个合法移动")

def test_apply_move():
    print("\n  测试3: 应用移动")
    s = AzulState(num_players=2, seed=42)
    moves = s.get_legal_moves()
    m = moves[0]
    s2 = s.apply_move(m)
    # 原状态不变
    assert s.current_player == 0
    # 新状态玩家切换
    assert s2.current_player == 1
    print(f"  ✅ 移动 {m} 应用成功")

def test_floor_overflow():
    print("\n  测试4: 瓷砖溢出到地板")
    s = AzulState(num_players=2, seed=42)
    # 找一个能触发溢出的移动（从工厂取砖但行已满）
    board = s.boards[0]
    # 手动填满第0行（只能放1块）
    board.pattern_lines[0] = [0, 1]  # 已满（蓝色×1）
    # 取一块蓝砖扔地板
    # 找含蓝砖的工厂
    for fi, f in enumerate(s.factories):
        if f.get(0, 0) > 0:
            m = Move(source=fi, color=0, target_row=FLOOR)
            s2 = s.apply_move(m)
            assert len(s2.boards[0].floor) > 0
            print(f"  ✅ 地板溢出: {len(s2.boards[0].floor)} 块")
            break

def test_scoring():
    print("\n  测试5: 贴砖计分（相邻连放）")
    from engine import AzulState
    s = AzulState(num_players=2, seed=0)
    board = s.boards[0]

    # 手动设置墙面：第0行放了 col=0,1,3
    board.wall[0][0] = True
    board.wall[0][1] = True
    board.wall[0][3] = True

    # 在 (0,2) 放砖，水平邻居有 col=1 和 col=3 不连续
    # 连续：左边col=1，自身col=2 → h_len=2
    pts = s._score_placement(board, 0, 2)
    print(f"  (0,2) 得分: {pts}分")

    # 在 (0,4) 放砖，左边col=3相邻 → h_len=2
    pts2 = s._score_placement(board, 0, 4)
    print(f"  (0,4) 得分: {pts2}分")

    # 孤立放砖
    board2 = s.boards[1]
    pts3 = s._score_placement(board2, 2, 2)
    assert pts3 == 1
    print(f"  孤立砖得分: {pts3}分 ✅")

def test_full_game():
    print("\n  测试6: 随机对局直到结束")
    import random
    s = AzulState(num_players=2, seed=123)
    rng = random.Random(123)
    steps = 0
    while not s.game_over and steps < 1000:
        moves = s.get_legal_moves()
        if not moves:
            break
        m = rng.choice(moves)
        s.apply_move_inplace(m)
        steps += 1

    print(f"  ✅ 对局完成，共 {steps} 步")
    print(f"  最终得分: {s.scores()}")
    print(f"  胜者: P{s.winner()}")
    s.render()

def test_wall_pattern():
    print("\n  测试7: 墙面布局正确性")
    for row in range(5):
        assert len(set(WALL_PATTERN[row])) == 5, f"第{row}行有重复颜色"
    for col in range(5):
        colors = [WALL_PATTERN[row][col] for row in range(5)]
        assert len(set(colors)) == 5, f"第{col}列有重复颜色"
    print("  ✅ 每行每列各色唯一")

if __name__ == "__main__":
    test_wall_pattern()
    test_basic()
    test_legal_moves()
    test_apply_move()
    test_floor_overflow()
    test_scoring()
    test_full_game()
    print("\n" + "━" * 50)
    print("  🎉 所有测试通过！")
    print("━" * 50)

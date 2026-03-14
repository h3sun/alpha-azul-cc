"""
pygbag 入口文件 — 花砖物语 (Azul)
部署到 GitHub Pages：python -m pygbag --build main.py
本地预览：        python -m pygbag main.py
"""

import asyncio
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(__file__))

print(f"[main] Python {sys.version}")
print(f"[main] platform: {sys.platform}")

try:
    import pygame
    print(f"[main] pygame OK: {pygame.version.ver}")
except Exception as e:
    print(f"[main] pygame FAILED: {e}")

try:
    from engine import AzulState
    print("[main] engine OK")
except Exception as e:
    print(f"[main] engine FAILED: {e}")
    traceback.print_exc()

try:
    from ai.mcts_agent import MCTSAgent
    print("[main] ai.mcts_agent OK")
except Exception as e:
    print(f"[main] ai.mcts_agent FAILED: {e}")
    traceback.print_exc()

try:
    from ui import AzulGame
    print("[main] ui OK")
except Exception as e:
    print(f"[main] ui FAILED: {e}")
    traceback.print_exc()


async def main():
    print("[main] starting game...")
    try:
        game = AzulGame(num_players=2, ai_players={1})
        print("[main] AzulGame created, entering run loop")
        await game.run()
    except Exception as e:
        print(f"[main] CRASH: {e}")
        traceback.print_exc()
        # 崩溃后保持循环，让 pygbag 不退出，错误才能显示
        while True:
            await asyncio.sleep(1)


asyncio.run(main())

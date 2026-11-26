"""Автотесты логики. Запуск: python -m unittest discover -s tests -v"""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import main


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = main.Game(seed=1234, headless=True)

    def setUp(self):
        self.game.reset(1234)
        self.game.start()

    def test_map_connected_and_eight_rooms(self):
        self.assertEqual(len(self.game.rooms), 8)
        seen = set()
        stack = [(1, 2)]
        while stack:
            coord = stack.pop()
            if coord in seen:
                continue
            seen.add(coord)
            stack.extend(self.game.rooms[coord].doors.values())
        self.assertEqual(seen, set(main.ROOM_LAYOUT))

    def test_combat_spawns_and_clears(self):
        g = self.game
        g._enter_room((2, 2), "W")
        self.assertFalse(g.room.cleared)
        self.assertGreaterEqual(len(g.room.enemies), 3)
        for enemy in list(g.room.enemies):
            g._kill_enemy(enemy)
        g._check_room_clear()
        self.assertTrue(g.room.cleared)
        self.assertEqual(g.combat_cleared, 1)
        self.assertGreaterEqual(len(g.room.pickups), 2)

    def test_friendly_bullet_kills_enemy(self):
        g = self.game
        g._enter_room((2, 2), "W")
        enemy = g.room.enemies[0]
        enemy.hp = 1
        g.bullets.append(main.Bullet(pygame.Vector2(enemy.pos), pygame.Vector2(0, 0), 5, 1, True))
        g._update_bullets(0.01)
        self.assertNotIn(enemy, g.room.enemies)
        self.assertEqual(g.kills, 1)

    def test_boss_door_locked_until_three_combats(self):
        g = self.game
        g._enter_room((1, 1), "N")
        for enemy in list(g.room.enemies):
            g._kill_enemy(enemy)
        g._check_room_clear()
        self.assertIsNotNone(g._door_lock((1, 0)))
        g.combat_cleared = 3
        self.assertIsNone(g._door_lock((1, 0)))

    def test_bomb_opens_secret_and_breaks_rocks(self):
        g = self.game
        g._enter_room((0, 1), "E")
        for enemy in list(g.room.enemies):
            g._kill_enemy(enemy)
        g._check_room_clear()
        door = main.door_center("N")
        near_door = pygame.Rect(int(door.x) - 20, int(door.y) + 20, 40, 40)
        g.room.rocks.append(near_door)
        g.player.pos = pygame.Vector2(main.INNER.centerx, main.INNER.bottom - 60)
        g._explode(pygame.Vector2(door.x, door.y + 35))
        self.assertTrue(g.secret_open)
        self.assertIsNone(g._door_lock((0, 0)))
        self.assertNotIn(near_door, g.room.rocks)

    def test_upgrades_apply(self):
        g = self.game
        p = g.player
        g._apply_upgrade(main.UPGRADES[0])
        self.assertEqual(p.damage, 1.5)
        g._apply_upgrade(main.UPGRADES[5])
        self.assertTrue(p.double)
        g._fire(pygame.Vector2(1, 0))
        self.assertEqual(len(g.bullets), 2)
        g._apply_upgrade(main.UPGRADES[3])
        self.assertEqual(p.max_hp, 8)

    def test_dash_grants_invulnerability(self):
        g = self.game
        g._dash()
        hp = g.player.hp
        g.damage_player(1)
        self.assertEqual(g.player.hp, hp)
        self.assertGreater(g.player.dash_cd, 0)

    def test_pause_freezes_run_time(self):
        g = self.game
        g.state = "paused"
        g.update(0.016)
        self.assertEqual(g.run_time, 0)
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)
        g.handle_event(event)
        self.assertEqual(g.state, "playing")

    def test_full_progression_to_victory(self):
        g = self.game
        # Кладовая даёт улучшение.
        g._enter_room((0, 2), "E")
        g.player.pos = pygame.Vector2(main.INNER.centerx, main.INNER.centery)
        g._update_pickups(0.016)
        self.assertEqual(len(g.room.pickups), 0)
        # Зачищаем три боевые комнаты.
        for coord, entry in [((2, 2), "W"), ((1, 1), "S"), ((0, 1), "E")]:
            g._enter_room(coord, entry)
            for enemy in list(g.room.enemies):
                g._kill_enemy(enemy)
            g._check_room_clear()
        self.assertEqual(g.combat_cleared, 3)
        # Бомба открывает тайник.
        g.player.pos = pygame.Vector2(main.INNER.centerx, main.INNER.bottom - 60)
        g._explode(pygame.Vector2(main.INNER.centerx, main.INNER.top + 30))
        self.assertTrue(g.secret_open)
        g._enter_room((0, 0), "S")
        g.player.hp = 2
        for pickup in list(g.room.pickups):
            g.player.pos = pygame.Vector2(pickup.pos)
            g._update_pickups(0.016)
        self.assertGreater(g.player.hp, 2)
        # Босс доступен и победа завершает забег.
        g._enter_room((1, 0), "W")
        boss = g.room.enemies[0]
        self.assertEqual(boss.kind, "boss")
        g._kill_enemy(boss)
        self.assertEqual(g.state, "won")
        g.draw()

    def test_death_and_restart(self):
        g = self.game
        g.player.invuln = 0
        g.damage_player(99)
        self.assertEqual(g.state, "dead")
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        self.assertEqual(g.state, "playing")
        self.assertEqual(g.player.hp, g.player.max_hp)

    def test_north_door_transition_from_start(self):
        g = self.game
        g.player.pos = pygame.Vector2(main.INNER.centerx, main.ARENA.top + 5)
        g._check_doors()
        self.assertEqual(g.coord, (1, 1))
        self.assertEqual(g.player.pos.y, main.INNER.bottom - 46)

    def test_cannot_leave_through_non_aligned_wall(self):
        g = self.game
        # Игрок у южной стены, но смещён к западу: южного проёма здесь нет.
        g.player.pos = pygame.Vector2(main.INNER.left + 40, main.ARENA.bottom + 20)
        g._check_doors()
        self.assertEqual(g.coord, (1, 2))
        self.assertLessEqual(g.player.pos.y, main.INNER.bottom - g.player.radius)

    def test_simulation_stability(self):
        g = self.game
        g._enter_room((1, 1), "S")
        for _ in range(300):
            g.update(1 / 60)
            g.draw()
        self.assertIn(g.state, ("playing", "dead"))


if __name__ == "__main__":
    unittest.main()

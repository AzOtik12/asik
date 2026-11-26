"""Подземье — небольшой рогалик в духе The Binding of Isaac.
Запуск:  python main.py
Управление: WASD — движение, стрелки — стрельба, Space — рывок,
B — бомба, P/Esc — пауза, M — звук, R — новая игра после победы/поражения.
Все спрайты рисуются кодом; сторонние изображения не нужны.
"""
from __future__ import annotations
import math
import random
import sys
from array import array
from dataclasses import dataclass, field
from pathlib import Path
import pygame

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1120, 760
FPS = 60
ARENA = pygame.Rect(40, 128, 824, 552)
INNER = pygame.Rect(62, 150, 780, 508)
PANEL = pygame.Rect(884, 128, 208, 552)
DOOR_HALF = 42
BG = (16, 22, 30)
FLOOR_A = (38, 48, 56)
FLOOR_B = (42, 53, 61)
WALL = (74, 86, 94)
WALL_DARK = (28, 36, 44)
INK = (232, 238, 240)
MUTED = (148, 163, 174)
GOLD = (244, 196, 82)
CYAN = (92, 220, 230)
RED = (235, 92, 92)
GREEN = (120, 210, 130)
PURPLE = (178, 130, 235)
ORANGE = (245, 150, 70)
DIRS = { "N ": (0, -1),  "S ": (0, 1),  "W ": (-1, 0),  "E ": (1, 0)}
OPPOSITE = { "N ":  "S ",  "S ":  "N ",  "W ":  "E ",  "E ":  "W "}
ROOM_LAYOUT = {
    (1, 2): ( "start ",  "Вход "),
    (0, 2): ( "treasure ",  "Кладовая "),
    (2, 2): ( "combat ",  "Грибной зал "),
    (1, 1): ( "combat ",  "Перекрёсток "),
    (0, 1): ( "combat ",  "Споровый грот "),
    (2, 1): ( "combat ",  "Караульня "),
    (1, 0): ( "boss ",  "Логово Стража "),
    (0, 0): ( "secret ",  "Тайник "),
}
COMBAT_TOTAL = 4
BOSS_REQUIRED = 3
UPGRADES = [
    ( "damage ",  "Острый кристалл ",  "+0.5 к урону снарядов ", RED),
    ( "rate ",  "Быстрые руки ",  "Скорострельность +18% ", CYAN),
    ( "speed ",  "Лёгкие сапоги ",  "+22 к скорости бега ", GREEN),
    ( "heart ",  "Сердце контейнер ",  "+2 к максимуму здоровья, лечит 2 ", RED),
    ( "pierce ",  "Пробивание ",  "Снаряды пробивают ещё одного врага ", PURPLE),
    ( "double ",  "Двойной выстрел ",  "Каждый выстрел выпускает 2 снаряда ", GOLD),
    ( "bomb_belt ",  "Сапёрный пояс ",  "+3 бомбы, лечит 2 HP ", ORANGE),
]

def clamp(value, low, high):
    return max(low, min(high, value))

def vec(x=0.0, y=0.0):
    if isinstance(x, (pygame.Vector2, tuple, list)):
        return pygame.Vector2(x)
    return pygame.Vector2(float(x), float(y))

def door_center(direction):
    if direction == "N":
        return vec(INNER.centerx, INNER.top)
    if direction == "S":
        return vec(INNER.centerx, INNER.bottom)
    if direction == "W":
        return vec(INNER.left, INNER.centery)
    return vec(INNER.right, INNER.centery)

def circle_rect_collision(pos, radius, rect):
    cx = clamp(pos.x, rect.left, rect.right)
    cy = clamp(pos.y, rect.top, rect.bottom)
    return (pos.x - cx) ** 2 + (pos.y - cy) ** 2 < radius * radius

def move_with_rocks(entity, delta, rocks):
    """Простое скольжение вдоль препятствий по осям."""
    entity.pos.x += delta.x
    for rock in rocks:
        if circle_rect_collision(entity.pos, entity.radius, rock):
            if delta.x > 0:
                entity.pos.x = rock.left - entity.radius
            elif delta.x < 0:
                entity.pos.x = rock.right + entity.radius
    entity.pos.y += delta.y
    for rock in rocks:
        if circle_rect_collision(entity.pos, entity.radius, rock):
            if delta.y > 0:
                entity.pos.y = rock.top - entity.radius
            elif delta.y < 0:
                entity.pos.y = rock.bottom + entity.radius

# ---------------------------------------------------------------------------
# Сущности
# ---------------------------------------------------------------------------
@dataclass
class Player:
    pos: pygame.Vector2
    radius: float = 14
    hp: int = 6
    max_hp: int = 6
    speed: float = 230
    damage: float = 1.0
    fire_delay: float = 0.23
    shot_timer: float = 0
    invuln: float = 0
    dash_timer: float = 0
    dash_cd: float = 0
    dash_dir: pygame.Vector2 = field(default_factory=lambda: vec(1, 0))
    facing: pygame.Vector2 = field(default_factory=lambda: vec(0, -1))
    pierce: int = 0
    double: bool = False
    bombs: int = 2
    coins: int = 0

@dataclass
class Enemy:
    kind: str
    pos: pygame.Vector2
    hp: float
    max_hp: float
    radius: float
    speed: float
    timer: float
    phase: float = 0
    charge_dir: pygame.Vector2 = field(default_factory=lambda: vec())
    charge_time: float = 0
    flash: float = 0
    summon_timer: float = 5

@dataclass
class Bullet:
    pos: pygame.Vector2
    vel: pygame.Vector2
    radius: float
    damage: float
    friendly: bool
    life: float = 1.15
    pierce: int = 0
    color: tuple = CYAN

@dataclass
class Pickup:
    kind: str
    pos: pygame.Vector2
    upgrade: tuple | None = None
    bob: float = 0

@dataclass
class Particle:
    pos: pygame.Vector2
    vel: pygame.Vector2
    life: float
    max_life: float
    color: tuple
    size: float

@dataclass
class FloatText:
    pos: pygame.Vector2
    text: str
    color: tuple
    life: float = 1.0

@dataclass
class Bomb:
    pos: pygame.Vector2
    fuse: float = 1.15

@dataclass
class Room:
    coord: tuple
    kind: str
    name: str
    doors: dict = field(default_factory=dict)
    enemies: list = field(default_factory=list)
    rocks: list = field(default_factory=list)
    pickups: list = field(default_factory=list)
    bombs: list = field(default_factory=list)
    cleared: bool = False
    visited: bool = False
    spawned: bool = False
    reward_given: bool = False

# ---------------------------------------------------------------------------
# Игра
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, seed=None, headless=False):
        # Звук необязателен: игра работает даже без аудиоустройства/библиотек.
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
        except (pygame.error, NotImplementedError, ImportError):
            pass
        pygame.init()
        self.headless = headless
        flags = pygame.SCALED if not headless else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.display.set_caption("Подземье — мини-рогалик")
        self.clock = pygame.time.Clock()
        self.font_dir = Path(__file__).resolve().parent / "assets"
        self.font_cache = {}
        self.muted = False
        self.sounds = {}
        try:
            self.sound_ok = pygame.mixer.get_init() is not None
        except (pygame.error, NotImplementedError, ImportError):
            self.sound_ok = False
        if self.sound_ok:
            self._make_sounds()
        self.anim = 0.0
        self.reset(seed)

    # -- звук ---------------------------------------------------------------
    def _tone(self, freq, duration, volume=0.22, slide=0.5):
        rate = 22050
        samples = array("h")
        for i in range(int(rate * duration)):
            t = i / rate
            f = freq * (1 + slide * t / max(duration, 0.01))
            env = (1 - t / duration) ** 2
            value = int(32767 * volume * env * math.sin(2 * math.pi * f * t))
            samples.append(value)
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _make_sounds(self):
        try:
            self.sounds = {
                "shoot": self._tone(620, 0.055, 0.10, -0.4),
                "hit": self._tone(180, 0.09, 0.18, -0.5),
                "pickup": self._tone(760, 0.13, 0.18, 0.6),
                "door": self._tone(300, 0.12, 0.15, 0.4),
                "boom": self._tone(70, 0.28, 0.30, -0.6),
                "win": self._tone(520, 0.45, 0.22, 1.0),
            }
        except pygame.error:
            self.sound_ok = False

    def play(self, name):
        if self.sound_ok and not self.muted and name in self.sounds:
            self.sounds[name].play()

    # -- генерация мира -----------------------------------------------------
    def reset(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        self.rng = random.Random(self.seed)
        self.state = "title"
        self.run_time = 0.0
        self.kills = 0
        self.combat_cleared = 0
        self.rooms_visited = 1
        self.damage_taken = 0
        self.secret_open = False
        self.shake = 0.0
        self.toast = ""
        self.toast_time = 0.0
        self.lock_hint_cd = 0.0
        self.bullets = []
        self.particles = []
        self.texts = []
        self.upgrade_pool = list(UPGRADES)
        self.rooms = {}
        for coord, (kind, name) in ROOM_LAYOUT.items():
            room = Room(coord, kind, name)
            x, y = coord
            for d, (dx, dy) in DIRS.items():
                other = (x + dx, y + dy)
                if other in ROOM_LAYOUT:
                    room.doors[d] = other
            room.cleared = kind in ("start", "treasure", "secret")
            self.rooms[coord] = room
        self.coord = (1, 2)
        self.room = self.rooms[self.coord]
        self.room.visited = True
        self.player = Player(pos=vec(INNER.centerx, INNER.centery + 70))
        self._make_rocks(self.room)
        treasure = self.rooms[(0, 2)]
        self._make_rocks(treasure)
        treasure.pickups.append(Pickup("upgrade", vec(INNER.centerx, INNER.centery), self._choose_upgrade()))
        secret = self.rooms[(0, 0)]
        secret.pickups.append(Pickup("upgrade", vec(INNER.centerx - 60, INNER.centery), self._choose_upgrade()))
        secret.pickups.append(Pickup("heart", vec(INNER.centerx + 60, INNER.centery)))
        for room in self.rooms.values():
            if room.kind in ("combat", "boss") and not room.rocks:
                self._make_rocks(room)

    def _choose_upgrade(self):
        if not self.upgrade_pool:
            self.upgrade_pool = list(UPGRADES)
        return self.rng.choice(self.upgrade_pool)

    def _make_rocks(self, room):
        if room.kind in ("start", "treasure", "secret"):
            room.rocks = []
            return
        candidates = [
            pygame.Rect(230, 250, 54, 54), pygame.Rect(620, 250, 54, 54),
            pygame.Rect(230, 470, 54, 54), pygame.Rect(620, 470, 54, 54),
            pygame.Rect(410, 330, 50, 50),
        ]
        if room.kind == "boss":
            room.rocks = candidates[:4]
        else:
            room.rocks = self.rng.sample(candidates, self.rng.randint(2, 4))

    def _free_spot(self, room, avoid_player=True):
        for _ in range(80):
            p = vec(self.rng.uniform(INNER.left + 70, INNER.right - 70),
                    self.rng.uniform(INNER.top + 70, INNER.bottom - 70))
            if any(circle_rect_collision(p, 34, r) for r in room.rocks):
                continue
            if avoid_player and p.distance_to(self.player.pos) < 170:
                continue
            if any(p.distance_to(e.pos) < 60 for e in room.enemies):
                continue
            return p
        return vec(INNER.centerx, INNER.top + 100)

    def _spawn_room(self, room):
        room.spawned = True
        if room.kind == "boss":
            room.enemies.append(Enemy("boss", vec(INNER.centerx, INNER.top + 130), 70, 70, 34, 58, 1.4))
            self.notify("СТРАЖ КОРНЕЙ проснулся!", RED)
            return
        if room.kind != "combat":
            return
        count = min(6, 3 + self.combat_cleared)
        kinds = ["crawler", "crawler", "spitter", "charger"]
        for _ in range(count):
            kind = self.rng.choice(kinds)
            pos = self._free_spot(room)
            stats = {
                "crawler": (3, 13, 82),
                "spitter": (4, 14, 66),
                "charger": (5, 16, 72),
            }[kind]
            room.enemies.append(Enemy(kind, pos, stats[0], stats[0], stats[1], stats[2], self.rng.uniform(0.7, 1.8)))

    def notify(self, text, color=INK):
        self.toast = text
        self.toast_color = color
        self.toast_time = 2.4

    def start(self):
        if self.state == "title":
            self.state = "playing"
            self.notify("Зачисти 3 боевых комнаты, чтобы открыть путь к боссу.", GOLD)

    # -- ввод ---------------------------------------------------------------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type != pygame.KEYDOWN:
            return True
        key = event.key
        if key == pygame.K_m:
            self.muted = not self.muted
            self.notify("Звук выключен" if self.muted else "Звук включён", MUTED)
        if self.state == "title" and key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.start()
        elif self.state == "playing":
            if key in (pygame.K_p, pygame.K_ESCAPE):
                self.state = "paused"
            elif key == pygame.K_SPACE:
                self._dash()
            elif key == pygame.K_b:
                self._place_bomb()
        elif self.state == "paused":
            if key in (pygame.K_p, pygame.K_ESCAPE, pygame.K_RETURN):
                self.state = "playing"
            elif key == pygame.K_r:
                self.reset()
                self.start()
        elif self.state in ("dead", "won") and key == pygame.K_r:
            self.reset()
            self.start()
        return True

    def _dash(self):
        p = self.player
        if p.dash_cd > 0:
            return
        keys = pygame.key.get_pressed()
        move = self._move_vector(keys)
        p.dash_dir = move if move.length_squared() else vec(p.facing)
        p.dash_timer = 0.16
        p.dash_cd = 1.15
        p.invuln = max(p.invuln, 0.2)
        self.burst(p.pos, CYAN, 8, speed=90)

    def _place_bomb(self):
        p = self.player
        if p.bombs <= 0:
            self.notify("Бомб нет. Ищи их после зачистки комнат.", MUTED)
            return
        p.bombs -= 1
        self.room.bombs.append(Bomb(vec(p.pos)))

    @staticmethod
    def _move_vector(keys):
        move = vec()
        if keys[pygame.K_a]:
            move.x -= 1
        if keys[pygame.K_d]:
            move.x += 1
        if keys[pygame.K_w]:
            move.y -= 1
        if keys[pygame.K_s]:
            move.y += 1
        if move.length_squared():
            move = move.normalize()
        return move

    @staticmethod
    def _shoot_vector(keys):
        shot = vec()
        if keys[pygame.K_LEFT]:
            shot.x -= 1
        if keys[pygame.K_RIGHT]:
            shot.x += 1
        if keys[pygame.K_UP]:
            shot.y -= 1
        if keys[pygame.K_DOWN]:
            shot.y += 1
        if shot.length_squared():
            shot = shot.normalize()
        return shot

    # -- обновление ---------------------------------------------------------
    def update(self, dt):
        dt = min(dt, 0.033)
        self.anim += dt
        self.shake = max(0, self.shake - dt * 30)
        self.toast_time = max(0, self.toast_time - dt)
        self.lock_hint_cd = max(0, self.lock_hint_cd - dt)
        self._update_particles(dt)
        if self.state != "playing":
            return
        self.run_time += dt
        keys = pygame.key.get_pressed()
        self._update_player(dt, keys)
        if self.state != "playing":
            return
        self._update_bombs(dt)
        self._update_enemies(dt)
        self._update_bullets(dt)
        self._update_pickups(dt)
        self._check_room_clear()
        self._check_doors()

    def _update_player(self, dt, keys):
        p = self.player
        p.shot_timer = max(0, p.shot_timer - dt)
        p.invuln = max(0, p.invuln - dt)
        p.dash_cd = max(0, p.dash_cd - dt)
        move = self._move_vector(keys)
        if p.dash_timer > 0:
            p.dash_timer -= dt
            delta = p.dash_dir * 640 * dt
            if self.rng.random() < 0.6:
                self.particles.append(Particle(vec(p.pos), vec(-p.dash_dir.x * 40, -p.dash_dir.y * 40), 0.25, 0.25, CYAN, 5))
        else:
            delta = move * p.speed * dt
            if move.length_squared():
                p.facing = vec(move)
        move_with_rocks(p, delta, self.room.rocks)
        shot = self._shoot_vector(keys)
        if shot.length_squared():
            p.facing = vec(shot)
            if p.shot_timer <= 0:
                self._fire(shot)
                p.shot_timer = p.fire_delay

    def _fire(self, direction):
        p = self.player
        perpendicular = vec(-direction.y, direction.x)
        offsets = [-6, 6] if p.double else [0]
        for offset in offsets:
            start = p.pos + direction * (p.radius + 6) + perpendicular * offset
            self.bullets.append(Bullet(start, direction * 540, 5, p.damage, True, pierce=p.pierce, color=CYAN))
        self.play("shoot")

    def _enemy_shot(self, pos, direction, speed=210, radius=6, color=ORANGE):
        if direction.length_squared() == 0:
            direction = vec(1, 0)
        self.bullets.append(Bullet(vec(pos), direction.normalize() * speed, radius, 1, False, life=3.0, color=color))

    def _update_enemies(self, dt):
        p = self.player
        for enemy in list(self.room.enemies):
            enemy.flash = max(0, enemy.flash - dt)
            enemy.timer -= dt
            to_player = p.pos - enemy.pos
            dist = to_player.length()
            direction = to_player.normalize() if dist else vec(1, 0)
            delta = vec()
            if enemy.kind == "crawler":
                delta = direction * enemy.speed * dt
            elif enemy.kind == "spitter":
                if dist > 220:
                    delta = direction * enemy.speed * dt
                elif dist < 150:
                    delta = -direction * enemy.speed * dt
                else:
                    delta = vec(-direction.y, direction.x) * enemy.speed * 0.5 * dt
                if enemy.timer <= 0:
                    self._enemy_shot(enemy.pos, direction, 225)
                    enemy.timer = 1.55
            elif enemy.kind == "charger":
                if enemy.charge_time > 0:
                    enemy.charge_time -= dt
                    delta = enemy.charge_dir * 360 * dt
                elif enemy.timer <= 0:
                    if enemy.phase == 0:
                        enemy.phase = 1
                        enemy.timer = 0.55
                        enemy.charge_dir = vec(direction)
                    else:
                        enemy.phase = 0
                        enemy.charge_time = 0.45
                        enemy.timer = 2.2
                else:
                    delta = direction * enemy.speed * dt
            elif enemy.kind == "boss":
                phase2 = enemy.hp <= enemy.max_hp * 0.5
                delta = direction * enemy.speed * (1.35 if phase2 else 1.0) * dt
                delta += vec(-direction.y, direction.x) * math.sin(self.anim * 1.4) * 35 * dt
                if enemy.timer <= 0:
                    n = 14 if phase2 else 10
                    base = self.anim * 0.7
                    for i in range(n):
                        angle = base + 2 * math.pi * i / n
                        self._enemy_shot(enemy.pos, vec(math.cos(angle), math.sin(angle)), 185 if phase2 else 160, 7, RED)
                    for spread in (-0.22, 0, 0.22):
                        angle = math.atan2(direction.y, direction.x) + spread
                        self._enemy_shot(enemy.pos, vec(math.cos(angle), math.sin(angle)), 245, 6, ORANGE)
                    enemy.timer = 1.35 if phase2 else 1.85
                if phase2:
                    enemy.summon_timer -= dt
                    minions = sum(1 for e in self.room.enemies if e.kind != "boss")
                    if enemy.summon_timer <= 0 and minions < 4:
                        enemy.summon_timer = 6
                        for _ in range(2):
                            pos = self._free_spot(self.room)
                            self.room.enemies.append(Enemy("crawler", pos, 3, 3, 13, 95, 1))
                        self.notify("Страж призывает помощников!", RED)
            # лёгкое расталкивание, чтобы враги не слипались
            for other in self.room.enemies:
                if other is enemy:
                    continue
                away = enemy.pos - other.pos
                d = away.length()
                min_d = enemy.radius + other.radius + 4
                if 0 < d < min_d:
                    delta += away.normalize() * (min_d - d) * 3 * dt
            move_with_rocks(enemy, delta, self.room.rocks)
            enemy.pos.x = clamp(enemy.pos.x, INNER.left + enemy.radius, INNER.right - enemy.radius)
            enemy.pos.y = clamp(enemy.pos.y, INNER.top + enemy.radius, INNER.bottom - enemy.radius)
            if p.pos.distance_to(enemy.pos) < p.radius + enemy.radius:
                self.damage_player(1)

    def _update_bullets(self, dt):
        p = self.player
        for bullet in list(self.bullets):
            bullet.life -= dt
            bullet.pos += bullet.vel * dt
            dead = bullet.life <= 0 or not INNER.collidepoint(bullet.pos)
            if not dead and any(circle_rect_collision(bullet.pos, bullet.radius, r) for r in self.room.rocks):
                self.burst(bullet.pos, MUTED, 3, speed=50)
                dead = True
            if not dead and bullet.friendly:
                for enemy in list(self.room.enemies):
                    if bullet.pos.distance_to(enemy.pos) < bullet.radius + enemy.radius:
                        enemy.hp -= bullet.damage
                        enemy.flash = 0.1
                        self.burst(bullet.pos, enemy_color(enemy.kind), 4, speed=80)
                        if enemy.hp <= 0:
                            self._kill_enemy(enemy)
                        if bullet.pierce > 0:
                            bullet.pierce -= 1
                        else:
                            dead = True
                        break
            elif not dead and not bullet.friendly:
                if bullet.pos.distance_to(p.pos) < bullet.radius + p.radius:
                    self.damage_player(1)
                    dead = True
            if dead and bullet in self.bullets:
                self.bullets.remove(bullet)

    def _kill_enemy(self, enemy):
        if enemy not in self.room.enemies:
            return
        self.room.enemies.remove(enemy)
        self.kills += 1
        self.burst(enemy.pos, enemy_color(enemy.kind), 16, speed=150)
        self.shake = max(self.shake, 4)
        self.play("hit")
        if enemy.kind == "boss":
            self.state = "won"
            self.play("win")
            self.burst(enemy.pos, GOLD, 60, speed=240)
            return
        if self.rng.random() < 0.45:
            self.room.pickups.append(Pickup("coin", vec(enemy.pos)))

    def damage_player(self, amount):
        p = self.player
        if p.invuln > 0 or p.dash_timer > 0 or self.state != "playing":
            return
        p.hp -= amount
        self.damage_taken += amount
        p.invuln = 1.0
        self.shake = 9
        self.burst(p.pos, RED, 12, speed=140)
        self.play("hit")
        if p.hp <= 0:
            p.hp = 0
            self.state = "dead"

    def _update_bombs(self, dt):
        for bomb in list(self.room.bombs):
            bomb.fuse -= dt
            if bomb.fuse <= 0:
                self.room.bombs.remove(bomb)
                self._explode(bomb.pos)

    def _explode(self, pos):
        radius = 110
        self.shake = 14
        self.play("boom")
        self.burst(pos, ORANGE, 40, speed=260)
        self.burst(pos, GOLD, 20, speed=160)
        for enemy in list(self.room.enemies):
            if enemy.pos.distance_to(pos) < radius + enemy.radius:
                enemy.hp -= 10 if enemy.kind == "boss" else 8
                enemy.flash = 0.15
                if enemy.hp <= 0:
                    self._kill_enemy(enemy)
        self.room.rocks = [r for r in self.room.rocks if vec(r.center).distance_to(pos) > radius + 20]
        if self.player.pos.distance_to(pos) < radius * 0.75:
            self.damage_player(1)
        if not self.secret_open:
            for d, target in self.room.doors.items():
                if self.rooms[target].kind == "secret" and door_center(d).distance_to(pos) < radius + 45:
                    self.secret_open = True
                    self.notify("Тайная комната открыта!", PURPLE)
                    self.play("door")

    def _update_pickups(self, dt):
        p = self.player
        for pickup in list(self.room.pickups):
            pickup.bob += dt
            dist = pickup.pos.distance_to(p.pos)
            if pickup.kind == "coin" and dist < 85:
                pickup.pos += (p.pos - pickup.pos).normalize() * 260 * dt if dist else vec()
            if pickup.kind == "heart" and p.hp >= p.max_hp:
                continue
            if dist < p.radius + 18:
                self.room.pickups.remove(pickup)
                self.play("pickup")
                if pickup.kind == "coin":
                    p.coins += 1
                    self.texts.append(FloatText(vec(p.pos), "+1 монета", GOLD))
                elif pickup.kind == "heart":
                    p.hp = min(p.max_hp, p.hp + 2)
                    self.texts.append(FloatText(vec(p.pos), "+2 здоровья", RED))
                elif pickup.kind == "bomb":
                    p.bombs += 1
                    self.texts.append(FloatText(vec(p.pos), "+1 бомба", ORANGE))
                elif pickup.kind == "upgrade" and pickup.upgrade:
                    self._apply_upgrade(pickup.upgrade)

    def _apply_upgrade(self, upgrade):
        uid, name, desc, color = upgrade
        p = self.player
        if uid == "damage":
            p.damage += 0.5
        elif uid == "rate":
            p.fire_delay = max(0.09, p.fire_delay * 0.82)
        elif uid == "speed":
            p.speed = min(330, p.speed + 22)
        elif uid == "heart":
            p.max_hp += 2
            p.hp = min(p.max_hp, p.hp + 2)
        elif uid == "pierce":
            p.pierce += 1
        elif uid == "double":
            p.double = True
        elif uid == "bomb_belt":
            p.bombs += 3
            p.hp = min(p.max_hp, p.hp + 2)
        if uid in ("pierce", "double") and upgrade in self.upgrade_pool:
            self.upgrade_pool.remove(upgrade)
        self.notify(f"{name}: {desc}", color)
        self.burst(p.pos, color, 24, speed=160)
        self.texts.append(FloatText(vec(p.pos.x, p.pos.y - 30), name, color, 1.6))

    def _check_room_clear(self):
        room = self.room
        if room.spawned and not room.cleared and not room.enemies:
            room.cleared = True
            self.play("door")
            if room.kind == "combat":
                self.combat_cleared += 1
                self.notify(f"Комната зачищена! Боевых комнат: {self.combat_cleared}/{BOSS_REQUIRED} для босса.", GREEN)
                center = vec(INNER.centerx, INNER.centery)
                for i in range(self.rng.randint(2, 4)):
                    self.room.pickups.append(Pickup("coin", center + vec(self.rng.uniform(-60, 60), self.rng.uniform(-40, 40))))
                if self.rng.random() < 0.4:
                    self.room.pickups.append(Pickup("heart", center + vec(0, 60)))
                if self.rng.random() < 0.3:
                    self.room.pickups.append(Pickup("bomb", center + vec(60, 0)))
                if self.combat_cleared % 2 == 0 and not room.reward_given:
                    room.reward_given = True
                    room.pickups.append(Pickup("upgrade", center, self._choose_upgrade()))

    def _door_lock(self, target):
        if not self.room.cleared:
            return "Сначала победи всех врагов!"
        if self.rooms[target].kind == "boss" and self.combat_cleared < BOSS_REQUIRED:
            return f"Печать босса: зачисти ещё {BOSS_REQUIRED - self.combat_cleared} боевых комнаты."
        if self.rooms[target].kind == "secret" and not self.secret_open:
            return "Треснувшая стена. Подорви её бомбой (B)."
        return None

    def _check_doors(self):
        p = self.player
        aligned = None
        best = float("inf")
        for d in self.room.doors:
            center = door_center(d)
            perp = abs(p.pos.x - center.x) if d in ("N", "S") else abs(p.pos.y - center.y)
            dist = p.pos.distance_to(center)
            if perp < DOOR_HALF - 10 and dist < best:
                aligned, best = d, dist
        near_door = aligned is not None and best < 90
        lock = self._door_lock(self.room.doors[aligned]) if near_door else "wall"
        # Стены удерживают игрока, кроме открытого проёма рядом с ним.
        if not near_door or lock is not None:
            p.pos.x = clamp(p.pos.x, INNER.left + p.radius, INNER.right - p.radius)
            p.pos.y = clamp(p.pos.y, INNER.top + p.radius, INNER.bottom - p.radius)
            if near_door and lock is not None and self.lock_hint_cd <= 0:
                self.notify(lock, GOLD)
                self.lock_hint_cd = 1.5
            return
        center = door_center(aligned)
        # В самом проёме не даём выйти через боковые края двери.
        margin = DOOR_HALF - p.radius
        if aligned in ("N", "S"):
            if (aligned == "N" and p.pos.y < INNER.top) or (aligned == "S" and p.pos.y > INNER.bottom):
                p.pos.x = clamp(p.pos.x, center.x - margin, center.x + margin)
        else:
            if (aligned == "W" and p.pos.x < INNER.left) or (aligned == "E" and p.pos.x > INNER.right):
                p.pos.y = clamp(p.pos.y, center.y - margin, center.y + margin)
        if p.pos.y < ARENA.top + 10 and aligned == "N":
            self._enter_room(self.room.doors["N"], "S")
        elif p.pos.y > ARENA.bottom - 10 and aligned == "S":
            self._enter_room(self.room.doors["S"], "N")
        elif p.pos.x < ARENA.left + 10 and aligned == "W":
            self._enter_room(self.room.doors["W"], "E")
        elif p.pos.x > ARENA.right - 10 and aligned == "E":
            self._enter_room(self.room.doors["E"], "W")

    def _enter_room(self, coord, entry):
        self.coord = coord
        self.room = self.rooms[coord]
        self.bullets.clear()
        center = door_center(entry)
        inward = {"N": vec(0, 1), "S": vec(0, -1), "W": vec(1, 0), "E": vec(-1, 0)}[entry]
        self.player.pos = center + inward * 46
        self.player.invuln = max(self.player.invuln, 0.8)
        if not self.room.visited:
            self.room.visited = True
            self.rooms_visited += 1
        if not self.room.spawned:
            self._spawn_room(self.room)
        self.play("door")
        if self.room.kind == "secret":
            self.notify("Тайник найден! Забирай улучшение и сердце.", PURPLE)
        elif self.room.kind == "treasure":
            self.notify("Кладовая: улучшение ждёт в центре.", GOLD)

    def _update_particles(self, dt):
        for particle in list(self.particles):
            particle.life -= dt
            particle.pos += particle.vel * dt
            particle.vel *= max(0, 1 - 3 * dt)
            if particle.life <= 0:
                self.particles.remove(particle)
        for text in list(self.texts):
            text.life -= dt
            text.pos.y -= 28 * dt
            if text.life <= 0:
                self.texts.remove(text)

    def burst(self, pos, color, count, speed=120):
        for _ in range(count):
            angle = self.rng.uniform(0, 2 * math.pi)
            v = self.rng.uniform(speed * 0.3, speed)
            life = self.rng.uniform(0.25, 0.6)
            self.particles.append(Particle(vec(pos), vec(math.cos(angle) * v, math.sin(angle) * v), life, life, color, self.rng.uniform(2, 5)))

    # -- отрисовка ----------------------------------------------------------
    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.font_cache:
            name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            path = self.font_dir / name
            self.font_cache[key] = pygame.font.Font(str(path) if path.exists() else None, size)
        return self.font_cache[key]

    def text(self, surface, value, size, pos, color=INK, anchor="topleft", bold=False):
        img = self.font(size, bold).render(str(value), True, color)
        rect = img.get_rect(**{anchor: pos})
        surface.blit(img, rect)
        return rect

    def draw(self):
        frame = pygame.Surface((WIDTH, HEIGHT))
        frame.fill(BG)
        self._draw_background(frame)
        self._draw_arena(frame)
        self._draw_hud(frame)
        self._draw_bottom(frame)
        if self.toast_time > 0 and self.state == "playing":
            alpha = min(255, int(self.toast_time * 400))
            img = self.font(16, True).render(self.toast, True, getattr(self, "toast_color", INK))
            img.set_alpha(alpha)
            rect = img.get_rect(midtop=(ARENA.centerx, 92))
            frame.blit(img, rect)
        if self.state == "title":
            self._draw_title(frame)
        elif self.state == "paused":
            self._draw_overlay(frame, "ПАУЗА", "P / Esc / Enter — продолжить", "R — начать заново", CYAN)
        elif self.state == "dead":
            self._draw_end(frame, False)
        elif self.state == "won":
            self._draw_end(frame, True)
        offset = (0, 0)
        if self.shake > 0 and self.state == "playing":
            offset = (self.rng.uniform(-self.shake, self.shake), self.rng.uniform(-self.shake, self.shake))
        self.screen.blit(frame, offset)
        pygame.display.flip()

    def _draw_background(self, s):
        for x in range(0, WIDTH, 40):
            pygame.draw.line(s, (20, 28, 36), (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 40):
            pygame.draw.line(s, (20, 28, 36), (0, y), (WIDTH, y))
        self.text(s, "ПОДЗЕМЬЕ", 28, (40, 28), INK, bold=True)
        self.text(s, "мини-рогалик", 15, (40, 66), MUTED)
        self.text(s, f"Забег #{self.seed:06d}", 16, (WIDTH - 40, 34), GOLD, anchor="topright")
        mm = int(self.run_time // 60)
        ss = int(self.run_time % 60)
        self.text(s, f"Время {mm:02d}:{ss:02d}", 16, (WIDTH - 40, 60), MUTED, anchor="topright")

    def _draw_arena(self, s):
        pygame.draw.rect(s, WALL_DARK, ARENA.inflate(16, 16), border_radius=18)
        pygame.draw.rect(s, WALL, ARENA, border_radius=14)
        pygame.draw.rect(s, FLOOR_A, INNER, border_radius=6)
        tile = 42
        for yy in range(INNER.top, INNER.bottom, tile):
            for xx in range(INNER.left, INNER.right, tile):
                if ((xx - INNER.left) // tile + (yy - INNER.top) // tile) % 2 == 0:
                    pygame.draw.rect(s, FLOOR_B, (xx, yy, min(tile, INNER.right - xx), min(tile, INNER.bottom - yy)))
        # дверные проёмы
        for d, target in self.room.doors.items():
            center = door_center(d)
            lock = self._door_lock(target)
            horizontal = d in ("N", "S")
            rect = pygame.Rect(0, 0, DOOR_HALF * 2, 30) if horizontal else pygame.Rect(0, 0, 30, DOOR_HALF * 2)
            rect.center = (int(center.x), int(center.y))
            color = (24, 32, 40) if lock is None else (60, 48, 44)
            pygame.draw.rect(s, color, rect, border_radius=5)
            pygame.draw.rect(s, GOLD if lock is None else RED, rect, 3, border_radius=5)
            if self.rooms[target].kind == "secret" and not self.secret_open:
                pygame.draw.line(s, MUTED, rect.topleft, rect.bottomright, 2)
                pygame.draw.line(s, MUTED, rect.topright, rect.bottomleft, 2)
                self.text(s, "B", 14, rect.center, ORANGE, anchor="center", bold=True)
            elif self.rooms[target].kind == "boss":
                self.text(s, "БОСС", 12, rect.center, RED if lock else GOLD, anchor="center", bold=True)
        for rock in self.room.rocks:
            pygame.draw.rect(s, (30, 38, 44), rock.move(4, 6), border_radius=10)
            pygame.draw.rect(s, (92, 104, 110), rock, border_radius=10)
            pygame.draw.rect(s, (120, 132, 138), rock.inflate(-14, -18), border_radius=7)
            pygame.draw.line(s, (66, 78, 84), rock.midleft, rock.midright, 2)
        for pickup in self.room.pickups:
            self._draw_pickup(s, pickup)
        for bomb in self.room.bombs:
            pulse = 1 + 0.12 * math.sin(self.anim * 18)
            pygame.draw.circle(s, (30, 30, 34), bomb.pos, 13)
            pygame.draw.circle(s, ORANGE if bomb.fuse < 0.4 else MUTED, bomb.pos, int(13 * pulse), 2)
            pygame.draw.line(s, GOLD, (bomb.pos.x, bomb.pos.y - 12), (bomb.pos.x + 6, bomb.pos.y - 20), 2)
            self.text(s, f"{bomb.fuse:.1f}", 11, (bomb.pos.x, bomb.pos.y - 30), ORANGE, anchor="center")
        for enemy in sorted(self.room.enemies, key=lambda e: e.pos.y):
            self._draw_enemy(s, enemy)
        self._draw_player(s)
        for bullet in self.bullets:
            pygame.draw.circle(s, bullet.color, bullet.pos, int(bullet.radius) + 3)
            pygame.draw.circle(s, INK, bullet.pos, max(2, int(bullet.radius) - 2))
        for particle in self.particles:
            alpha = max(0, particle.life / particle.max_life)
            size = max(1, int(particle.size * alpha))
            pygame.draw.circle(s, particle.color, particle.pos, size)
        for text in self.texts:
            img = self.font(14, True).render(text.text, True, text.color)
            img.set_alpha(int(255 * clamp(text.life, 0, 1)))
            s.blit(img, img.get_rect(center=text.pos))
        boss = next((e for e in self.room.enemies if e.kind == "boss"), None)
        if boss:
            bar = pygame.Rect(INNER.left + 120, INNER.top + 14, INNER.width - 240, 14)
            pygame.draw.rect(s, (30, 30, 34), bar, border_radius=7)
            fill = bar.copy()
            fill.width = int(bar.width * clamp(boss.hp / boss.max_hp, 0, 1))
            pygame.draw.rect(s, RED, fill, border_radius=7)
            self.text(s, "СТРАЖ КОРНЕЙ", 13, (bar.centerx, bar.top - 4), INK, anchor="midbottom", bold=True)

    def _draw_player(self, s):
        p = self.player
        if p.invuln > 0 and int(self.anim * 14) % 2 == 0 and p.dash_timer <= 0:
            return
        x, y = p.pos
        bob = math.sin(self.anim * 10) * 1.5
        pygame.draw.ellipse(s, (20, 28, 34), (x - 16, y + 10, 32, 10))
        pygame.draw.circle(s, (44, 92, 110), (x, y + bob), 16)
        pygame.draw.circle(s, CYAN, (x, y - 3 + bob), 13)
        pygame.draw.circle(s, (220, 245, 245), (x - 4, y - 5 + bob), 4)
        pygame.draw.circle(s, (220, 245, 245), (x + 5, y - 5 + bob), 4)
        pygame.draw.circle(s, BG, (x - 4 + p.facing.x * 2, y - 5 + p.facing.y * 2 + bob), 2)
        pygame.draw.circle(s, BG, (x + 5 + p.facing.x * 2, y - 5 + p.facing.y * 2 + bob), 2)
        if p.dash_cd <= 0:
            pygame.draw.circle(s, GOLD, (x, y + 24), 3)

    def _draw_enemy(self, s, enemy):
        x, y = enemy.pos
        color = (255, 255, 255) if enemy.flash > 0 else enemy_color(enemy.kind)
        pygame.draw.ellipse(s, (20, 28, 34), (x - enemy.radius, y + enemy.radius - 5, enemy.radius * 2, 10))
        if enemy.kind == "crawler":
            pygame.draw.circle(s, color, (x, y), enemy.radius)
            pygame.draw.circle(s, (60, 40, 50), (x - 4, y - 2), 3)
            pygame.draw.circle(s, (60, 40, 50), (x + 5, y - 2), 3)
        elif enemy.kind == "spitter":
            pygame.draw.circle(s, color, (x, y + 3), enemy.radius)
            pygame.draw.circle(s, (230, 210, 160), (x, y - 8), enemy.radius - 3)
            pygame.draw.circle(s, BG, (x, y + 5), 5)
        elif enemy.kind == "charger":
            rect = pygame.Rect(x - enemy.radius, y - enemy.radius, enemy.radius * 2, enemy.radius * 2)
            pygame.draw.rect(s, color, rect, border_radius=6)
            pygame.draw.polygon(s, GOLD, [(x - 8, y - enemy.radius), (x, y - enemy.radius - 10), (x + 8, y - enemy.radius)])
            pygame.draw.circle(s, BG, (x - 5, y), 3)
            pygame.draw.circle(s, BG, (x + 5, y), 3)
            if enemy.phase == 1 and enemy.charge_time <= 0:
                end = enemy.pos + enemy.charge_dir * 90
                pygame.draw.line(s, RED, enemy.pos, end, 3)
        elif enemy.kind == "boss":
            for i in range(8):
                angle = self.anim * 0.6 + i * math.pi / 4
                px = x + math.cos(angle) * (enemy.radius + 8)
                py = y + math.sin(angle) * (enemy.radius + 8)
                pygame.draw.circle(s, (70, 130, 80), (px, py), 10)
            pygame.draw.circle(s, color, (x, y), enemy.radius)
            pygame.draw.circle(s, (230, 240, 200), (x, y), enemy.radius - 10)
            look = (self.player.pos - enemy.pos)
            look = look.normalize() * 6 if look.length() else vec()
            pygame.draw.circle(s, RED, (x + look.x, y + look.y), 12)
            pygame.draw.circle(s, BG, (x + look.x, y + look.y), 6)
        if enemy.kind != "boss" and enemy.hp < enemy.max_hp:
            bar = pygame.Rect(x - 16, y - enemy.radius - 12, 32, 4)
            pygame.draw.rect(s, BG, bar)
            pygame.draw.rect(s, RED, (bar.x, bar.y, int(32 * enemy.hp / enemy.max_hp), 4))

    def _draw_pickup(self, s, pickup):
        x, y = pickup.pos.x, pickup.pos.y + math.sin(self.anim * 3 + pickup.bob) * 3
        if pickup.kind == "coin":
            pygame.draw.circle(s, GOLD, (x, y), 8)
            pygame.draw.circle(s, (180, 130, 40), (x, y), 5, 2)
        elif pickup.kind == "heart":
            draw_heart(s, (x, y), 10, RED)
        elif pickup.kind == "bomb":
            pygame.draw.circle(s, (40, 40, 46), (x, y), 10)
            pygame.draw.circle(s, ORANGE, (x, y), 10, 2)
            pygame.draw.line(s, GOLD, (x, y - 9), (x + 5, y - 16), 2)
        elif pickup.kind == "upgrade":
            color = pickup.upgrade[3] if pickup.upgrade else GOLD
            pygame.draw.circle(s, (30, 40, 48), (x, y + 12), 24)
            pygame.draw.circle(s, color, (x, y + 12), 24, 2)
            points = [(x, y - 16), (x + 13, y), (x, y + 16), (x - 13, y)]
            pygame.draw.polygon(s, color, points)
            pygame.draw.polygon(s, INK, points, 2)
            if pickup.upgrade:
                self.text(s, pickup.upgrade[1], 13, (x, y - 30), color, anchor="center", bold=True)

    def _draw_hud(self, s):
        p = self.player
        pygame.draw.rect(s, (24, 32, 40), PANEL, border_radius=14)
        pygame.draw.rect(s, (48, 60, 70), PANEL, 2, border_radius=14)
        x = PANEL.left + 18
        self.text(s, "ЗДОРОВЬЕ", 13, (x, PANEL.top + 16), MUTED, bold=True)
        for i in range(p.max_hp):
            hx = x + 10 + (i % 6) * 29
            hy = PANEL.top + 48 + (i // 6) * 26
            draw_heart(s, (hx, hy), 9, RED if i < p.hp else (58, 66, 74))
        y = PANEL.top + 78 + ((p.max_hp - 1) // 6) * 26
        stats = [
            ("Урон", f"{p.damage:g}"),
            ("Выстрелов/с", f"{1 / p.fire_delay:.1f}"),
            ("Скорость", f"{p.speed:g}"),
            ("Бомбы [B]", str(p.bombs)),
            ("Монеты", str(p.coins)),
        ]
        for label, value in stats:
            self.text(s, label, 13, (x, y), MUTED)
            self.text(s, value, 14, (PANEL.right - 18, y), INK, anchor="topright", bold=True)
            y += 24
        dash = "готов" if p.dash_cd <= 0 else f"{p.dash_cd:.1f}с"
        self.text(s, "Рывок [Space]", 13, (x, y), MUTED)
        self.text(s, dash, 14, (PANEL.right - 18, y), CYAN if p.dash_cd <= 0 else MUTED, anchor="topright", bold=True)
        y += 34
        self.text(s, "КАРТА", 13, (x, y), MUTED, bold=True)
        y += 26
        cell, gap = 36, 10
        map_x = x + 8
        for (cx, cy), room in self.rooms.items():
            if room.kind == "secret" and not self.secret_open and not room.visited:
                continue
            rx = map_x + cx * (cell + gap)
            ry = y + cy * (cell + gap)
            rect = pygame.Rect(rx, ry, cell, cell)
            known = room.visited or any(self.rooms[n].visited for n in room.doors.values())
            if not known:
                continue
            fill = (58, 70, 80) if room.visited else (32, 42, 50)
            if room.coord == self.coord:
                fill = (70, 100, 110)
            pygame.draw.rect(s, fill, rect, border_radius=5)
            pygame.draw.rect(s, GOLD if room.coord == self.coord else (70, 84, 94), rect, 2, border_radius=5)
            mark = ""
            if room.kind == "boss":
                mark = "Б"
            elif room.kind == "treasure":
                mark = "К"
            elif room.kind == "secret":
                mark = "?"
            elif room.visited and room.cleared and room.kind == "combat":
                mark = "✓"
            if mark:
                self.text(s, mark, 14, rect.center, GOLD if room.kind != "boss" else RED, anchor="center", bold=True)
        y += 3 * (cell + gap) + 12
        self.text(s, "ЦЕЛЬ", 13, (x, y), MUTED, bold=True)
        y += 24
        if self.combat_cleared < BOSS_REQUIRED:
            goal = f"Зачисти боевые комнаты: {self.combat_cleared}/{BOSS_REQUIRED}"
        elif self.rooms[(1, 0)].cleared:
            goal = "Страж побеждён!"
        else:
            goal = "Печать снята. Иди к боссу на севере карты."
        self._wrap_text(s, goal, 13, (x, y), PANEL.width - 36, INK)
        self.text(s, "B — бомба у треснувшей стены", 11, (x, PANEL.bottom - 44), MUTED)
        self.text(s, "К — кладовая, ? — тайник", 11, (x, PANEL.bottom - 26), MUTED)

    def _wrap_text(self, s, value, size, pos, width, color):
        words = value.split()
        line = ""
        y = pos[1]
        for word in words:
            test = f"{line} {word}".strip()
            if self.font(size).size(test)[0] > width and line:
                self.text(s, line, size, (pos[0], y), color)
                y += size + 5
                line = word
            else:
                line = test
        if line:
            self.text(s, line, size, (pos[0], y), color)

    def _draw_bottom(self, s):
        controls = "WASD — движение   Стрелки — стрельба   Space — рывок   B — бомба   P/Esc — пауза   M — звук"
        self.text(s, controls, 14, (WIDTH // 2, 716), MUTED, anchor="center")

    def _dim(self, s, alpha=190):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 18, alpha))
        s.blit(overlay, (0, 0))

    def _draw_title(self, s):
        self._dim(s, 210)
        cx = WIDTH // 2
        self.text(s, "ПОДЗЕМЬЕ", 64, (cx, 130), CYAN, anchor="center", bold=True)
        self.text(s, "Комнаты. Снаряды. Секреты. Один Страж.", 20, (cx, 200), INK, anchor="center")
        cards = [
            ("WASD", "движение"),
            ("СТРЕЛКИ", "стрельба"),
            ("SPACE", "рывок с неуязвимостью"),
            ("B", "бомба: враги, камни, тайные стены"),
        ]
        y = 270
        for key, desc in cards:
            pygame.draw.rect(s, (30, 42, 52), (cx - 300, y, 600, 52), border_radius=10)
            self.text(s, key, 18, (cx - 270, y + 26), GOLD, anchor="midleft", bold=True)
            self.text(s, desc, 17, (cx - 120, y + 26), INK, anchor="midleft")
            y += 64
        self.text(s, "Зачисти 3 боевые комнаты, найди улучшения и победи Стража Корней.", 16, (cx, 560), MUTED, anchor="center")
        pulse = 180 + int(75 * (0.5 + 0.5 * math.sin(self.anim * 3)))
        self.text(s, "Нажми ENTER, чтобы начать", 26, (cx, 620), (pulse, pulse, 210), anchor="center", bold=True)
        self.text(s, "Графика рисуется кодом · звук синтезируется · каждый забег уникален", 13, (cx, 680), MUTED, anchor="center")

    def _draw_overlay(self, s, title, line1, line2, color):
        self._dim(s)
        cx = WIDTH // 2
        self.text(s, title, 56, (cx, 280), color, anchor="center", bold=True)
        self.text(s, line1, 22, (cx, 370), INK, anchor="center")
        self.text(s, line2, 18, (cx, 420), MUTED, anchor="center")

    def _draw_end(self, s, won):
        self._dim(s, 215)
        cx = WIDTH // 2
        title = "СТРАЖ ПОВЕРЖЕН!" if won else "ЗАБЕГ ОКОНЧЕН"
        color = GOLD if won else RED
        self.text(s, title, 50, (cx, 200), color, anchor="center", bold=True)
        subtitle = "Подземье запомнит твою смелость." if won else "Спускайся снова — подземье меняется."
        self.text(s, subtitle, 19, (cx, 260), INK, anchor="center")
        mm = int(self.run_time // 60)
        ss = int(self.run_time % 60)
        score = self.player.coins * 10 + self.kills * 25 + self.combat_cleared * 100 + (1000 if won else 0)
        lines = [
            f"Время: {mm:02d}:{ss:02d}",
            f"Побеждено врагов: {self.kills}",
            f"Комнат посещено: {self.rooms_visited}",
            f"Монет собрано: {self.player.coins}",
            f"Очки: {score}",
        ]
        y = 330
        for line in lines:
            self.text(s, line, 21, (cx, y), INK, anchor="center")
            y += 40
        self.text(s, "R — новый забег", 26, (cx, 580), CYAN, anchor="center", bold=True)
        self.text(s, f"Забег #{self.seed:06d}", 14, (cx, 630), MUTED, anchor="center")

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running:
                    break
            self.update(dt)
            self.draw()
        pygame.quit()

def enemy_color(kind):
    return {
        "crawler": (210, 110, 130),
        "spitter": (200, 160, 90),
        "charger": (150, 110, 200),
        "boss": GREEN,
    }.get(kind, RED)

def draw_heart(surface, center, size, color):
    x, y = center
    pygame.draw.circle(surface, color, (x - size * 0.45, y - size * 0.25), size * 0.55)
    pygame.draw.circle(surface, color, (x + size * 0.45, y - size * 0.25), size * 0.55)
    pygame.draw.polygon(surface, color, [(x - size, y), (x + size, y), (x, y + size)])

def main():
    seed = None
    if len(sys.argv) > 1:
        try:
            seed = int(sys.argv[1])
        except ValueError:
            print("Использование: python main.py [числовой_seed]")
            return 1
    Game(seed=seed).run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

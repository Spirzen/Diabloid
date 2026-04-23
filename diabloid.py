import math
import os
import random
import sys
from dataclasses import dataclass

import pygame


pygame.init()

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

WORLD_WIDTH = 3200
WORLD_HEIGHT = 3200

COLORS = {
    "bg": (18, 18, 24),
    "grid": (30, 30, 40),
    "player": (80, 180, 255),
    "enemy": (230, 90, 90),
    "projectile": (255, 240, 140),
    "xp": (90, 255, 120),
    "ui_text": (245, 245, 245),
    "ui_muted": (160, 160, 170),
    "bar_bg": (50, 50, 65),
    "hp": (70, 220, 110),
    "exp": (95, 160, 255),
    "overlay": (10, 10, 12),
    "enemy_fast": (255, 140, 90),
    "enemy_tank": (170, 70, 200),
    "enemy_ranged": (255, 100, 180),
    "boss": (255, 70, 70),
    "enemy_projectile": (255, 170, 170),
}

HIGH_SCORE_FILE = "highscore.txt"


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def lerp(a, b, t):
    return a + (b - a) * t


@dataclass
class Upgrade:
    key: str
    title: str
    description: str


@dataclass
class Weapon:
    key: str
    title: str
    cooldown: float
    timer: float = 0.0
    level: int = 1


@dataclass
class CharacterPreset:
    key: str
    name: str
    description: str
    color: tuple
    hp_mult: float
    speed_bonus: float
    damage_bonus: float
    regen_bonus: float
    crit_bonus: float


CHARACTER_PRESETS = [
    CharacterPreset(
        "balanced",
        "Wanderer",
        "Сбалансированный старт.",
        (80, 180, 255),
        hp_mult=1.0,
        speed_bonus=0.0,
        damage_bonus=0.0,
        regen_bonus=0.0,
        crit_bonus=0.0,
    ),
    CharacterPreset(
        "tank",
        "Bulwark",
        "Больше HP, медленнее.",
        (120, 220, 150),
        hp_mult=1.35,
        speed_bonus=-40.0,
        damage_bonus=2.0,
        regen_bonus=0.8,
        crit_bonus=0.0,
    ),
    CharacterPreset(
        "assassin",
        "Shade",
        "Быстрый и критовый, но хрупкий.",
        (220, 180, 255),
        hp_mult=0.82,
        speed_bonus=45.0,
        damage_bonus=3.0,
        regen_bonus=0.0,
        crit_bonus=0.08,
    ),
]


WAVE_TABLE = [
    {
        "duration": 50,
        "spawn_a": 0.86,
        "spawn_b": 0.50,
        "batch_a": 1.0,
        "batch_b": 1.8,
        "weights": {"normal": 0.80, "fast": 0.20, "ranged": 0.00, "tank": 0.00},
        "boss": False,
    },
    {
        "duration": 60,
        "spawn_a": 0.52,
        "spawn_b": 0.34,
        "batch_a": 1.6,
        "batch_b": 2.8,
        "weights": {"normal": 0.55, "fast": 0.23, "ranged": 0.17, "tank": 0.05},
        "boss": True,
    },
    {
        "duration": 65,
        "spawn_a": 0.38,
        "spawn_b": 0.24,
        "batch_a": 2.5,
        "batch_b": 4.0,
        "weights": {"normal": 0.40, "fast": 0.24, "ranged": 0.20, "tank": 0.16},
        "boss": True,
    },
]


class Player:
    def __init__(self, preset):
        self.x = WORLD_WIDTH / 2
        self.y = WORLD_HEIGHT / 2
        self.radius = 18
        self.color = preset.color
        self.base_speed = 260.0 + preset.speed_bonus

        self.level = 1
        self.exp = 0
        self.exp_to_next = 45

        self.max_hp = int(120 * preset.hp_mult)
        self.hp = float(self.max_hp)
        self.regen = 0.0 + preset.regen_bonus
        self.armor = 0.0
        self.lifesteal = 0.0

        self.damage = 16 + preset.damage_bonus
        self.projectile_speed = 540.0
        self.pierce = 0
        self.crit_chance = 0.05 + preset.crit_bonus
        self.crit_mult = 1.75
        self.aoe_bonus = 0.0

        self.pickup_range = 60.0
        self.move_speed_bonus = 0.0
        self.weapons = {
            "magic_bolt": Weapon("magic_bolt", "Magic Bolt", cooldown=0.48),
            "orbit_blade": Weapon("orbit_blade", "Orbit Blades", cooldown=1.0),
            "nova": Weapon("nova", "Arcane Nova", cooldown=2.8),
            "frost_fan": Weapon("frost_fan", "Frost Fan", cooldown=1.6),
            "chain_burst": Weapon("chain_burst", "Chain Burst", cooldown=2.2),
        }
        self.unlocked_weapons = {"magic_bolt"}

    @property
    def speed(self):
        return self.base_speed + self.move_speed_bonus

    def move(self, dt, keys):
        dx = float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(keys[pygame.K_w] or keys[pygame.K_UP])
        if dx == 0 and dy == 0:
            return
        length = math.hypot(dx, dy)
        self.x += (dx / length) * self.speed * dt
        self.y += (dy / length) * self.speed * dt
        margin = self.radius
        self.x = clamp(self.x, margin, WORLD_WIDTH - margin)
        self.y = clamp(self.y, margin, WORLD_HEIGHT - margin)

    def gain_exp(self, amount):
        self.exp += amount
        level_ups = 0
        while self.exp >= self.exp_to_next:
            self.exp -= self.exp_to_next
            self.level += 1
            self.exp_to_next = int(self.exp_to_next * 1.22 + 12)
            level_ups += 1
        return level_ups

    def roll_damage(self, base):
        damage = base
        if random.random() < self.crit_chance:
            damage *= self.crit_mult
        return damage

    def apply_upgrade(self, upgrade_key):
        if upgrade_key == "damage":
            self.damage += 5
        elif upgrade_key == "speed":
            self.move_speed_bonus += 35
        elif upgrade_key == "fire_rate":
            for weapon in self.weapons.values():
                weapon.cooldown = max(0.12, weapon.cooldown * 0.9)
        elif upgrade_key == "max_hp":
            self.max_hp += 30
            self.hp += 30
        elif upgrade_key == "regen":
            self.regen += 1.2
        elif upgrade_key == "magnet":
            self.pickup_range += 28
        elif upgrade_key == "pierce":
            self.pierce += 1
        elif upgrade_key == "armor":
            self.armor = min(0.65, self.armor + 0.08)
        elif upgrade_key == "crit":
            self.crit_chance = min(0.65, self.crit_chance + 0.06)
        elif upgrade_key == "lifesteal":
            self.lifesteal = min(0.35, self.lifesteal + 0.03)
        elif upgrade_key == "aoe":
            self.aoe_bonus += 0.12
        elif upgrade_key == "projectile_speed":
            self.projectile_speed += 55
        elif upgrade_key.startswith("unlock_"):
            self.unlocked_weapons.add(upgrade_key.replace("unlock_", ""))
        elif upgrade_key.startswith("weapon_lvl_"):
            weapon_key = upgrade_key.replace("weapon_lvl_", "")
            if weapon_key in self.weapons:
                self.weapons[weapon_key].level += 1
        self.hp = clamp(self.hp, 0, self.max_hp)


class Enemy:
    def __init__(self, x, y, hp, speed, damage, radius, kind="normal", color=None):
        self.x = x
        self.y = y
        self.radius = radius
        self.max_hp = hp
        self.hp = float(hp)
        self.speed = speed
        self.damage = damage
        self.xp_drop = 7 + int(hp * 0.15)
        self.kind = kind
        self.color = color or COLORS["enemy"]
        self.shoot_timer = random.uniform(1.2, 2.8) if kind == "ranged" else 0.0
        self.boss_attack_timer = 0.0
        self.boss_state_timer = 0.0
        self.boss_mode = "burst"
        self.boss_spiral_angle = 0.0

    def update(self, dt, player):
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0 and (self.kind not in {"ranged"} or dist > 290):
            self.x += (dx / dist) * self.speed * dt
            self.y += (dy / dist) * self.speed * dt
        return dist

    def take_damage(self, amount):
        self.hp -= amount
        return self.hp <= 0


class Projectile:
    def __init__(self, x, y, vx, vy, damage, pierce, radius=6, life=1.15, color=None):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.damage = damage
        self.pierce = pierce
        self.life = life
        self.color = color or COLORS["projectile"]

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        out_of_world = self.x < 0 or self.x > WORLD_WIDTH or self.y < 0 or self.y > WORLD_HEIGHT
        return self.life <= 0 or out_of_world


class XpOrb:
    def __init__(self, x, y, amount):
        self.x = x
        self.y = y
        self.amount = amount
        self.radius = 5 + min(6, amount // 12)

    def update(self, dt, player):
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist < player.pickup_range * 2.2 and dist > 0:
            pull = clamp(220 + player.pickup_range * 2.4, 220, 680)
            self.x += (dx / dist) * pull * dt
            self.y += (dy / dist) * pull * dt
        return dist <= player.pickup_range


def get_spawn_position(pad=40):
    side = random.randint(0, 3)
    if side == 0:
        return random.uniform(0, WORLD_WIDTH), -pad
    if side == 1:
        return random.uniform(0, WORLD_WIDTH), WORLD_HEIGHT + pad
    if side == 2:
        return -pad, random.uniform(0, WORLD_HEIGHT)
    return WORLD_WIDTH + pad, random.uniform(0, WORLD_HEIGHT)


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Diabloid Survivors")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 22)
        self.font_small = pygame.font.SysFont("Consolas", 18)
        self.font_big = pygame.font.SysFont("Consolas", 44, bold=True)
        self.font_mid = pygame.font.SysFont("Consolas", 28, bold=True)

        self.best_time = self.load_best_time()
        self.selected_character_idx = 0
        self.state = "menu"
        self.running = True
        self.reset()

    def load_best_time(self):
        try:
            if os.path.exists(HIGH_SCORE_FILE):
                with open(HIGH_SCORE_FILE, "r", encoding="utf-8") as file:
                    return float(file.read().strip())
        except (ValueError, OSError):
            return 0.0
        return 0.0

    def save_best_time(self):
        try:
            with open(HIGH_SCORE_FILE, "w", encoding="utf-8") as file:
                file.write(f"{self.best_time:.2f}")
        except OSError:
            pass

    def reset(self):
        self.player = Player(CHARACTER_PRESETS[self.selected_character_idx])
        self.enemies = []
        self.projectiles = []
        self.enemy_projectiles = []
        self.xp_orbs = []

        self.game_over = False
        self.paused_for_upgrade = False
        self.pending_levelups = 0
        self.upgrade_options = []
        self.boss_spawned_for_wave = set()

        self.survival_time = 0.0
        self.spawn_timer = 0.0
        self.contact_damage_timer = 0.0

    def get_wave_state(self):
        time_left = self.survival_time
        wave_idx = 0
        for idx, wave in enumerate(WAVE_TABLE):
            if time_left <= wave["duration"]:
                wave_idx = idx
                progress = clamp(time_left / wave["duration"], 0.0, 1.0)
                return wave_idx, progress, wave
            time_left -= wave["duration"]
        last = WAVE_TABLE[-1]
        bonus_progress = clamp(time_left / 90.0, 0.0, 1.0)
        scale = 1.0 + min(2.0, time_left / 120.0)
        wave = {
            "duration": 9999,
            "spawn_a": max(0.08, last["spawn_a"] / scale),
            "spawn_b": max(0.05, last["spawn_b"] / (scale + 0.2)),
            "batch_a": last["batch_a"] * scale,
            "batch_b": last["batch_b"] * (scale + 0.4),
            "weights": {"normal": 0.28, "fast": 0.24, "ranged": 0.22, "tank": 0.26},
            "boss": True,
        }
        return len(WAVE_TABLE), bonus_progress, wave

    def create_enemy(self, enemy_type):
        x, y = get_spawn_position()
        wave_idx, progress, _ = self.get_wave_state()
        power = 1.0 + wave_idx * 0.55 + progress * 0.5
        if enemy_type == "fast":
            return Enemy(x, y, hp=18 * power, speed=132 + power * 18, damage=7 + power * 2.2, radius=11, kind="fast", color=COLORS["enemy_fast"])
        if enemy_type == "tank":
            return Enemy(x, y, hp=56 * power, speed=64 + power * 8, damage=12 + power * 3.0, radius=20, kind="tank", color=COLORS["enemy_tank"])
        if enemy_type == "ranged":
            return Enemy(x, y, hp=30 * power, speed=76 + power * 8, damage=8 + power * 2.3, radius=13, kind="ranged", color=COLORS["enemy_ranged"])
        if enemy_type == "boss":
            boss = Enemy(x, y, hp=300 * power, speed=86 + power * 4, damage=20 + power * 4.0, radius=34, kind="boss", color=COLORS["boss"])
            boss.boss_attack_timer = 1.6
            boss.boss_state_timer = 7.0
            return boss
        return Enemy(x, y, 25 * power, 86 + power * 9, 7 + power * 2.0, 14, kind="normal")

    def spawn_enemy(self):
        _, _, wave = self.get_wave_state()
        roll = random.random()
        acc = 0.0
        chosen = "normal"
        for key, weight in wave["weights"].items():
            acc += weight
            if roll <= acc:
                chosen = key
                break
        self.enemies.append(self.create_enemy(chosen))

    def spawn_miniboss(self):
        self.enemies.append(self.create_enemy("boss"))

    def roll_upgrades(self):
        pool = [
            Upgrade("damage", "Damage Boost", "+5 урона от снарядов"),
            Upgrade("speed", "Swift Boots", "+35 к скорости движения"),
            Upgrade("fire_rate", "Rapid Shot", "Скорострельность +10%"),
            Upgrade("max_hp", "Vitality", "+30 к максимальному HP"),
            Upgrade("regen", "Blood Ritual", "+1.2 HP/сек"),
            Upgrade("magnet", "Magnet", "Больше радиус подбора опыта"),
            Upgrade("pierce", "Piercing Shot", "Снаряды пробивают +1 цель"),
            Upgrade("armor", "Steel Skin", "Снижение входящего урона +8%"),
            Upgrade("crit", "Lethal Eye", "+6% шанс крита"),
            Upgrade("lifesteal", "Dark Pact", "+3% вампиризм от урона"),
            Upgrade("aoe", "Amplifier", "Увеличивает размер взрывных атак"),
            Upgrade("projectile_speed", "Ballistics", "+55 к скорости снарядов"),
        ]
        for key, title in [
            ("orbit_blade", "Orbit Blade"),
            ("nova", "Arcane Nova"),
            ("frost_fan", "Frost Fan"),
            ("chain_burst", "Chain Burst"),
        ]:
            if key not in self.player.unlocked_weapons:
                pool.append(Upgrade(f"unlock_{key}", title, f"Разблокирует оружие {title}"))
            else:
                pool.append(Upgrade(f"weapon_lvl_{key}", f"{title}+", "Усиление оружия"))
        pool.append(Upgrade("weapon_lvl_magic_bolt", "Magic Bolt+", "Усиление базового оружия"))
        self.upgrade_options = random.sample(pool, 3)
        self.paused_for_upgrade = True

    def get_nearest_enemy(self):
        if not self.enemies:
            return None
        return min(self.enemies, key=lambda e: (e.x - self.player.x) ** 2 + (e.y - self.player.y) ** 2)

    def get_nearest_enemies(self, count):
        return sorted(self.enemies, key=lambda e: (e.x - self.player.x) ** 2 + (e.y - self.player.y) ** 2)[:count]

    def shoot_magic_bolt(self, weapon):
        target = self.get_nearest_enemy()
        if target is None:
            return
        dx = target.x - self.player.x
        dy = target.y - self.player.y
        dist = math.hypot(dx, dy)
        if dist == 0:
            return
        spread = 0.09 * (weapon.level - 1)
        shots = 1 + (weapon.level - 1) // 3
        for shot_idx in range(shots):
            angle = math.atan2(dy, dx)
            if shots > 1:
                angle += (shot_idx - (shots - 1) / 2) * spread
            vx = math.cos(angle) * self.player.projectile_speed
            vy = math.sin(angle) * self.player.projectile_speed
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    vx,
                    vy,
                    self.player.roll_damage(self.player.damage + (weapon.level - 1) * 3),
                    self.player.pierce,
                    radius=6,
                    life=1.15,
                )
            )

    def shoot_orbit_blades(self, weapon):
        blades = 2 + weapon.level
        damage = self.player.roll_damage(self.player.damage * 0.75 + weapon.level * 4)
        speed = self.player.projectile_speed * 0.8
        for i in range(blades):
            angle = (math.tau / blades) * i + random.uniform(-0.08, 0.08)
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    damage,
                    pierce=1 + self.player.pierce,
                    radius=5,
                    life=1.4,
                    color=(160, 220, 255),
                )
            )

    def shoot_nova(self, weapon):
        bullets = 10 + weapon.level * 2
        damage = self.player.roll_damage(self.player.damage * 0.55 + weapon.level * 3)
        speed = 340 + weapon.level * 30
        size = int(4 + self.player.aoe_bonus * 8)
        for i in range(bullets):
            angle = (math.tau / bullets) * i
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    damage,
                    pierce=0,
                    radius=size,
                    life=0.95,
                    color=(210, 160, 255),
                )
            )

    def shoot_frost_fan(self, weapon):
        target = self.get_nearest_enemy()
        if target is None:
            return
        center = math.atan2(target.y - self.player.y, target.x - self.player.x)
        arrows = 4 + weapon.level
        spread = 0.28 + weapon.level * 0.02
        damage = self.player.roll_damage(self.player.damage * 0.7 + weapon.level * 2)
        for i in range(arrows):
            t = i / max(1, arrows - 1)
            angle = center + lerp(-spread, spread, t)
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * (self.player.projectile_speed + 90),
                    math.sin(angle) * (self.player.projectile_speed + 90),
                    damage,
                    pierce=0,
                    radius=5,
                    life=0.8,
                    color=(140, 220, 255),
                )
            )

    def shoot_chain_burst(self, weapon):
        jumps = 2 + weapon.level
        targets = self.get_nearest_enemies(jumps)
        for target in targets:
            damage = self.player.roll_damage(self.player.damage * 0.9 + weapon.level * 4)
            if target.take_damage(damage):
                self.enemies.remove(target)
                self.xp_orbs.append(XpOrb(target.x, target.y, target.xp_drop))
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    (target.x - self.player.x) * 7,
                    (target.y - self.player.y) * 7,
                    0,
                    0,
                    radius=3,
                    life=0.08,
                    color=(255, 255, 180),
                )
            )

    def update_weapons(self, dt):
        for key in self.player.unlocked_weapons:
            weapon = self.player.weapons[key]
            weapon.timer -= dt
            if weapon.timer <= 0:
                weapon.timer = weapon.cooldown
                if key == "magic_bolt":
                    self.shoot_magic_bolt(weapon)
                elif key == "orbit_blade":
                    self.shoot_orbit_blades(weapon)
                elif key == "nova":
                    self.shoot_nova(weapon)
                elif key == "frost_fan":
                    self.shoot_frost_fan(weapon)
                elif key == "chain_burst":
                    self.shoot_chain_burst(weapon)

    def shoot_enemy_projectile(self, enemy, angle=None, speed=None):
        if angle is None:
            angle = math.atan2(self.player.y - enemy.y, self.player.x - enemy.x)
        bullet_speed = speed or (250 + self.survival_time * 0.7)
        self.enemy_projectiles.append(
            Projectile(
                enemy.x,
                enemy.y,
                math.cos(angle) * bullet_speed,
                math.sin(angle) * bullet_speed,
                damage=enemy.damage * 0.9,
                pierce=0,
                radius=6,
                life=2.4,
                color=COLORS["enemy_projectile"],
            )
        )

    def update_boss_pattern(self, boss, dt):
        boss.boss_state_timer -= dt
        if boss.boss_state_timer <= 0:
            boss.boss_mode = random.choice(["burst", "spiral", "dash"])
            boss.boss_state_timer = 6.5
            boss.boss_attack_timer = 0.1

        boss.boss_attack_timer -= dt
        if boss.boss_mode == "burst":
            if boss.boss_attack_timer <= 0:
                count = 10
                for i in range(count):
                    angle = (math.tau / count) * i
                    self.shoot_enemy_projectile(boss, angle=angle, speed=250)
                boss.boss_attack_timer = 1.6
        elif boss.boss_mode == "spiral":
            if boss.boss_attack_timer <= 0:
                boss.boss_spiral_angle += 0.42
                self.shoot_enemy_projectile(boss, angle=boss.boss_spiral_angle, speed=280)
                self.shoot_enemy_projectile(boss, angle=boss.boss_spiral_angle + math.pi, speed=280)
                boss.boss_attack_timer = 0.12
        elif boss.boss_mode == "dash":
            if boss.boss_attack_timer <= 0:
                angle = math.atan2(self.player.y - boss.y, self.player.x - boss.x)
                boss.x += math.cos(angle) * 220
                boss.y += math.sin(angle) * 220
                boss.x = clamp(boss.x, 20, WORLD_WIDTH - 20)
                boss.y = clamp(boss.y, 20, WORLD_HEIGHT - 20)
                for i in range(6):
                    self.shoot_enemy_projectile(boss, angle=angle + random.uniform(-0.6, 0.6), speed=320)
                boss.boss_attack_timer = 1.1

    def world_to_screen(self, wx, wy, camera_x, camera_y):
        return int(wx - camera_x), int(wy - camera_y)

    def kill_player(self):
        self.player.hp = 0
        self.game_over = True
        self.state = "over"
        if self.survival_time > self.best_time:
            self.best_time = self.survival_time
            self.save_best_time()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if self.state == "menu":
                    if event.key == pygame.K_LEFT:
                        self.selected_character_idx = (self.selected_character_idx - 1) % len(CHARACTER_PRESETS)
                    elif event.key == pygame.K_RIGHT:
                        self.selected_character_idx = (self.selected_character_idx + 1) % len(CHARACTER_PRESETS)
                    elif event.key == pygame.K_RETURN:
                        self.reset()
                        self.state = "game"
                elif self.state == "over" and event.key == pygame.K_RETURN:
                    self.reset()
                    self.state = "game"
                elif event.key == pygame.K_ESCAPE:
                    self.state = "menu"

                if self.paused_for_upgrade:
                    if event.key in (pygame.K_1, pygame.K_KP1):
                        self.choose_upgrade(0)
                    elif event.key in (pygame.K_2, pygame.K_KP2):
                        self.choose_upgrade(1)
                    elif event.key in (pygame.K_3, pygame.K_KP3):
                        self.choose_upgrade(2)

    def choose_upgrade(self, idx):
        if idx >= len(self.upgrade_options):
            return
        self.player.apply_upgrade(self.upgrade_options[idx].key)
        self.paused_for_upgrade = False
        self.pending_levelups -= 1
        if self.pending_levelups > 0:
            self.roll_upgrades()

    def update(self, dt):
        if self.state != "game" or self.game_over or self.paused_for_upgrade:
            return

        self.survival_time += dt
        wave_idx, wave_progress, wave = self.get_wave_state()

        keys = pygame.key.get_pressed()
        self.player.move(dt, keys)
        self.player.hp = clamp(self.player.hp + self.player.regen * dt, 0, self.player.max_hp)
        self.update_weapons(dt)

        if wave["boss"] and wave_idx not in self.boss_spawned_for_wave:
            self.spawn_miniboss()
            self.boss_spawned_for_wave.add(wave_idx)

        spawn_interval = lerp(wave["spawn_a"], wave["spawn_b"], wave_progress)
        spawn_interval = max(0.06, spawn_interval)
        self.spawn_timer -= dt
        while self.spawn_timer <= 0:
            self.spawn_timer += spawn_interval
            batch = int(max(1, round(lerp(wave["batch_a"], wave["batch_b"], wave_progress))))
            for _ in range(batch):
                self.spawn_enemy()

        for enemy in self.enemies:
            dist = enemy.update(dt, self.player)
            if enemy.kind == "ranged":
                enemy.shoot_timer -= dt
                if enemy.shoot_timer <= 0 and dist < 540:
                    self.shoot_enemy_projectile(enemy)
                    enemy.shoot_timer = max(0.55, 2.1 - wave_idx * 0.18)
            elif enemy.kind == "boss":
                self.update_boss_pattern(enemy, dt)

        self.contact_damage_timer -= dt
        if self.contact_damage_timer <= 0:
            touching = [enemy for enemy in self.enemies if math.hypot(enemy.x - self.player.x, enemy.y - self.player.y) < enemy.radius + self.player.radius]
            if touching:
                total_damage = sum(enemy.damage for enemy in touching)
                total_damage *= 1.0 - self.player.armor
                self.player.hp -= total_damage
                self.contact_damage_timer = 0.28
                if self.player.hp <= 0:
                    self.kill_player()

        alive_projectiles = []
        for projectile in self.projectiles:
            if projectile.update(dt):
                continue
            if projectile.damage <= 0:
                alive_projectiles.append(projectile)
                continue

            should_delete = False
            for enemy in list(self.enemies):
                if math.hypot(enemy.x - projectile.x, enemy.y - projectile.y) <= enemy.radius + projectile.radius:
                    dealt = projectile.damage
                    if enemy.take_damage(dealt):
                        self.enemies.remove(enemy)
                        self.xp_orbs.append(XpOrb(enemy.x, enemy.y, enemy.xp_drop))
                    if self.player.lifesteal > 0:
                        self.player.hp = clamp(self.player.hp + dealt * self.player.lifesteal * 0.03, 0, self.player.max_hp)
                    if projectile.pierce > 0:
                        projectile.pierce -= 1
                    else:
                        should_delete = True
                        break
            if not should_delete:
                alive_projectiles.append(projectile)
        self.projectiles = alive_projectiles

        alive_enemy_projectiles = []
        for projectile in self.enemy_projectiles:
            if projectile.update(dt):
                continue
            if math.hypot(projectile.x - self.player.x, projectile.y - self.player.y) <= projectile.radius + self.player.radius:
                self.player.hp -= projectile.damage * (1.0 - self.player.armor)
                if self.player.hp <= 0:
                    self.kill_player()
                continue
            alive_enemy_projectiles.append(projectile)
        self.enemy_projectiles = alive_enemy_projectiles

        remaining_orbs = []
        for orb in self.xp_orbs:
            if orb.update(dt, self.player):
                gained = self.player.gain_exp(orb.amount)
                if gained > 0:
                    self.pending_levelups += gained
                    if not self.paused_for_upgrade:
                        self.roll_upgrades()
            else:
                remaining_orbs.append(orb)
        self.xp_orbs = remaining_orbs

    def draw_world(self, camera_x, camera_y):
        self.screen.fill(COLORS["bg"])
        for x in range(0, WORLD_WIDTH + 1, 80):
            sx0, sy0 = self.world_to_screen(x, 0, camera_x, camera_y)
            sx1, sy1 = self.world_to_screen(x, WORLD_HEIGHT, camera_x, camera_y)
            pygame.draw.line(self.screen, COLORS["grid"], (sx0, sy0), (sx1, sy1), 1)
        for y in range(0, WORLD_HEIGHT + 1, 80):
            sx0, sy0 = self.world_to_screen(0, y, camera_x, camera_y)
            sx1, sy1 = self.world_to_screen(WORLD_WIDTH, y, camera_x, camera_y)
            pygame.draw.line(self.screen, COLORS["grid"], (sx0, sy0), (sx1, sy1), 1)

        for orb in self.xp_orbs:
            sx, sy = self.world_to_screen(orb.x, orb.y, camera_x, camera_y)
            pygame.draw.circle(self.screen, COLORS["xp"], (sx, sy), orb.radius)
        for enemy in self.enemies:
            sx, sy = self.world_to_screen(enemy.x, enemy.y, camera_x, camera_y)
            pygame.draw.circle(self.screen, enemy.color, (sx, sy), int(enemy.radius))
            if enemy.kind == "boss":
                pygame.draw.circle(self.screen, (255, 230, 230), (sx, sy), int(enemy.radius), 2)
        for projectile in self.projectiles:
            sx, sy = self.world_to_screen(projectile.x, projectile.y, camera_x, camera_y)
            pygame.draw.circle(self.screen, projectile.color, (sx, sy), int(projectile.radius))
        for projectile in self.enemy_projectiles:
            sx, sy = self.world_to_screen(projectile.x, projectile.y, camera_x, camera_y)
            pygame.draw.circle(self.screen, projectile.color, (sx, sy), int(projectile.radius))

        px, py = self.world_to_screen(self.player.x, self.player.y, camera_x, camera_y)
        pygame.draw.circle(self.screen, self.player.color, (px, py), self.player.radius)
        pygame.draw.circle(self.screen, (255, 255, 255), (px, py), int(self.player.pickup_range), 1)

    def draw_ui(self):
        hp_ratio = self.player.hp / self.player.max_hp if self.player.max_hp else 0
        exp_ratio = self.player.exp / self.player.exp_to_next if self.player.exp_to_next else 0
        wave_idx, wave_progress, _ = self.get_wave_state()

        hp_rect = pygame.Rect(20, 20, 380, 18)
        exp_rect = pygame.Rect(20, 46, 380, 14)
        wave_rect = pygame.Rect(20, 66, 380, 10)

        pygame.draw.rect(self.screen, COLORS["bar_bg"], hp_rect)
        pygame.draw.rect(self.screen, COLORS["hp"], (hp_rect.x, hp_rect.y, int(hp_rect.w * hp_ratio), hp_rect.h))
        pygame.draw.rect(self.screen, COLORS["bar_bg"], exp_rect)
        pygame.draw.rect(self.screen, COLORS["exp"], (exp_rect.x, exp_rect.y, int(exp_rect.w * exp_ratio), exp_rect.h))
        pygame.draw.rect(self.screen, COLORS["bar_bg"], wave_rect)
        pygame.draw.rect(self.screen, (255, 190, 120), (wave_rect.x, wave_rect.y, int(wave_rect.w * wave_progress), wave_rect.h))

        timer_text = self.font.render(f"Time: {int(self.survival_time // 60):02d}:{int(self.survival_time % 60):02d}", True, COLORS["ui_text"])
        info_text = self.font.render(
            f"Lvl {self.player.level}  HP {int(self.player.hp)}/{self.player.max_hp}  DMG {int(self.player.damage)}  Wave {wave_idx + 1}  Best {int(self.best_time // 60):02d}:{int(self.best_time % 60):02d}",
            True,
            COLORS["ui_text"],
        )
        controls_text = self.font_small.render("WASD move  1/2/3 upgrades  Enter restart  Esc menu", True, COLORS["ui_muted"])
        self.screen.blit(timer_text, (SCREEN_WIDTH - timer_text.get_width() - 20, 18))
        self.screen.blit(info_text, (20, 82))
        self.screen.blit(controls_text, (20, SCREEN_HEIGHT - 30))

    def draw_upgrade_overlay(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((*COLORS["overlay"], 220))
        self.screen.blit(overlay, (0, 0))
        title = self.font_big.render("Level Up!", True, COLORS["ui_text"])
        subtitle = self.font.render("Выбери улучшение (1/2/3)", True, COLORS["ui_muted"])
        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 100))
        self.screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 160))
        for i, upgrade in enumerate(self.upgrade_options):
            rect = pygame.Rect(220, 250 + i * 120, SCREEN_WIDTH - 440, 96)
            pygame.draw.rect(self.screen, (36, 36, 48), rect, border_radius=10)
            pygame.draw.rect(self.screen, (95, 95, 125), rect, 2, border_radius=10)
            self.screen.blit(self.font.render(f"[{i + 1}]", True, COLORS["exp"]), (rect.x + 18, rect.y + 16))
            self.screen.blit(self.font.render(upgrade.title, True, COLORS["ui_text"]), (rect.x + 70, rect.y + 15))
            self.screen.blit(self.font_small.render(upgrade.description, True, COLORS["ui_muted"]), (rect.x + 70, rect.y + 52))

    def draw_game_over(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((*COLORS["overlay"], 220))
        self.screen.blit(overlay, (0, 0))
        self.screen.blit(self.font_big.render("Game Over", True, (255, 120, 120)), (SCREEN_WIDTH // 2 - 140, 250))
        self.screen.blit(
            self.font.render(f"Выжито: {int(self.survival_time // 60):02d}:{int(self.survival_time % 60):02d}", True, COLORS["ui_text"]),
            (SCREEN_WIDTH // 2 - 150, 320),
        )
        self.screen.blit(
            self.font.render(f"Рекорд: {int(self.best_time // 60):02d}:{int(self.best_time % 60):02d}", True, COLORS["exp"]),
            (SCREEN_WIDTH // 2 - 150, 360),
        )
        self.screen.blit(self.font.render("Нажми Enter для новой попытки", True, COLORS["ui_muted"]), (SCREEN_WIDTH // 2 - 225, 400))

    def draw_menu(self):
        self.screen.fill(COLORS["bg"])
        preset = CHARACTER_PRESETS[self.selected_character_idx]
        title = self.font_big.render("DIABLOID SURVIVORS", True, COLORS["ui_text"])
        pick = self.font_mid.render("Выбор персонажа", True, COLORS["exp"])
        card = pygame.Rect(SCREEN_WIDTH // 2 - 300, 250, 600, 190)
        pygame.draw.rect(self.screen, (32, 32, 44), card, border_radius=14)
        pygame.draw.rect(self.screen, (90, 90, 122), card, 2, border_radius=14)
        pygame.draw.circle(self.screen, preset.color, (card.x + 70, card.y + 95), 34)
        self.screen.blit(self.font.render(f"<  {preset.name}  >", True, COLORS["ui_text"]), (card.x + 130, card.y + 36))
        self.screen.blit(self.font_small.render(preset.description, True, COLORS["ui_muted"]), (card.x + 130, card.y + 76))
        stats = f"HP x{preset.hp_mult:.2f} | Speed {preset.speed_bonus:+.0f} | Damage {preset.damage_bonus:+.0f} | Crit {preset.crit_bonus * 100:+.0f}%"
        self.screen.blit(self.font_small.render(stats, True, COLORS["ui_muted"]), (card.x + 130, card.y + 110))

        self.screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 120))
        self.screen.blit(pick, (SCREEN_WIDTH // 2 - pick.get_width() // 2, 200))
        self.screen.blit(self.font.render("Enter - начать", True, COLORS["exp"]), (SCREEN_WIDTH // 2 - 95, 470))
        self.screen.blit(self.font_small.render("Left/Right: выбрать персонажа", True, COLORS["ui_muted"]), (SCREEN_WIDTH // 2 - 160, 510))
        self.screen.blit(self.font_small.render("Esc: выйти в меню из игры", True, COLORS["ui_muted"]), (SCREEN_WIDTH // 2 - 150, 536))
        self.screen.blit(
            self.font.render(f"Лучшее выживание: {int(self.best_time // 60):02d}:{int(self.best_time % 60):02d}", True, COLORS["ui_text"]),
            (SCREEN_WIDTH // 2 - 165, 580),
        )

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
            pygame.display.flip()
            return
        camera_x = clamp(self.player.x - SCREEN_WIDTH / 2, 0, WORLD_WIDTH - SCREEN_WIDTH)
        camera_y = clamp(self.player.y - SCREEN_HEIGHT / 2, 0, WORLD_HEIGHT - SCREEN_HEIGHT)
        self.draw_world(camera_x, camera_y)
        self.draw_ui()
        if self.paused_for_upgrade:
            self.draw_upgrade_overlay()
        if self.game_over:
            self.draw_game_over()
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
"""Diabloid Survivors — Python port of Java Survivors (Vampire Survivors–style arena)."""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

import pygame

pygame.init()

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
JAVA_ASSETS = BASE_DIR / "Java Survivors" / "assets"
SAVE_FILE = BASE_DIR / "survivors_save.json"

WIDTH = 1280
HEIGHT = 720
FPS = 120

# UI palette & layout
UI_MARGIN = 20
UI_ACCENT = (255, 198, 88)
UI_ACCENT_DIM = (180, 140, 60)
UI_TEXT = (240, 242, 248)
UI_TEXT_DIM = (150, 158, 175)
UI_PANEL = (14, 16, 28)
UI_PANEL_BORDER = (55, 68, 110)
UI_HP_FILL = (76, 217, 100)
UI_HP_BG = (55, 28, 32)
UI_XP_FILL = (100, 170, 255)
UI_XP_BG = (28, 32, 58)
UI_CARD = (38, 42, 68)
UI_CARD_HOVER = (52, 58, 92)
UI_SHOP_CARD = (72, 58, 38)
HUD_W = 440
HUD_PAD = 14
HUD_HEADER_H = 28
HUD_STAT_ROW_H = 30
HUD_STAT_ROWS = 3
HUD_STATS_GAP = 10
HUD_BAR_BLOCK_H = 56
HUD_STATS_H = HUD_STAT_ROWS * HUD_STAT_ROW_H
HUD_H = HUD_PAD * 2 + HUD_HEADER_H + HUD_STATS_H + HUD_STATS_GAP + HUD_BAR_BLOCK_H
WEAPON_ICON = 34
WEAPON_GAP = 6
WEAPON_BAR_PAD = 12
UPGRADE_CARD_W, UPGRADE_CARD_H = 640, 88
UPGRADE_CARD_GAP = 16
UPGRADE_START_Y = 220
SHOP_CARD_W, SHOP_CARD_H = 700, 76
SHOP_CARD_GAP = 14
SHOP_START_Y = 268
CONTACT_DAMAGE_TICK = 0.25
DASH_SPEED_MULTIPLIER = 4.5
DASH_DURATION = 0.15
DASH_COOLDOWN = 1.5


def ensure_assets() -> None:
    if not JAVA_ASSETS.is_dir():
        return
    ASSETS_DIR.mkdir(exist_ok=True)
    for src in JAVA_ASSETS.iterdir():
        if src.is_file():
            dst = ASSETS_DIR / src.name
            if not dst.exists():
                shutil.copy2(src, dst)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def distance_sq(x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x1 - x2, y1 - y2
    return dx * dx + dy * dy


def format_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


class GameState(Enum):
    MENU = auto()
    PLAYING = auto()
    GAME_OVER = auto()


class UpgradeState(Enum):
    NONE = auto()
    PAUSED_FOR_UPGRADE = auto()
    PAUSED_FOR_SHOP = auto()


class WeaponType(Enum):
    MAGIC_BOLT = auto()
    TRIPLE_CAST = auto()
    PULSE_RING = auto()
    PIERCE_LANCE = auto()
    DAMAGE_AURA = auto()
    CHAIN_LIGHTNING = auto()
    SAW_BLADE = auto()
    FROST_NOVA = auto()
    TOXIC_DART = auto()
    FLAME_ORB = auto()
    FIRE_WAVE = auto()
    FIRE_LANCE = auto()
    FIRE_METEOR = auto()
    ICE_SHARD = auto()
    ICE_SPIKE = auto()
    ICE_STORM = auto()
    WATER_JET = auto()
    WATER_ORB = auto()
    WATER_TIDE = auto()
    EARTH_SPIKE = auto()
    EARTH_QUAKE = auto()
    EARTH_BLADE = auto()
    THUNDER_SPEAR = auto()
    THUNDER_FIELD = auto()
    SHADOW_SCYTHE = auto()


EXTRA_WEAPON_START = WeaponType.FIRE_WAVE


class EnemyKind(Enum):
    NORMAL = auto()
    SPEEDER = auto()
    SHOOTER = auto()
    TANK = auto()
    BOSS = auto()


class StatusEffectType(Enum):
    SLOW = auto()
    BURN = auto()
    POISON = auto()
    SHIELD = auto()
    TEMP_DAMAGE_BOOST = auto()


class PerkBranch(Enum):
    ATTACK = "Атака"
    DEFENSE = "Защита"
    SUPPORT = "Поддержка"


@dataclass
class CharacterDef:
    name: str
    cost: int
    start_weapon: WeaponType
    damage_scale: float
    speed_scale: float


@dataclass
class StatusEffect:
    type: StatusEffectType
    duration: float
    power: float
    modifier: float
    tick_timer: float = 0.5


@dataclass
class DamageNumber:
    x: float
    y: float
    value: int
    alpha: float = 1.0


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float
    color: tuple
    circle: bool
    max_life: float = 0.0

    def __post_init__(self):
        if self.max_life <= 0:
            self.max_life = self.life


@dataclass
class LightningEffect:
    target: "Enemy"
    second_target: Optional["Enemy"] = None
    third_target: Optional["Enemy"] = None
    life: float = 0.15


@dataclass
class SawBladeEffect:
    x: float
    y: float
    angle: float
    speed: float
    radius: float
    damage: float
    pierce: int
    life: float = 1.8


@dataclass
class CoinPickup:
    x: float
    y: float
    value: int


@dataclass
class XpOrb:
    x: float
    y: float
    value: int


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    radius: float
    pierce: int
    life: float = 1.8
    from_enemy: bool = False
    applies_slow: bool = False
    applies_burn: bool = False
    applies_poison: bool = False


@dataclass
class Enemy:
    x: float
    y: float
    radius: float
    hp: float
    speed: float
    contact_damage: float
    xp_value: int
    score: int = 0
    hit_flash_timer: float = 0.0
    size_scale: float = 1.0
    speed_multiplier: float = 1.0
    attack_windup: float = 0.0
    effects: list = field(default_factory=list)
    kind: EnemyKind = EnemyKind.NORMAL
    attack_cooldown: float = 0.0
    phase: int = 1

    def take_damage(self, damage: float) -> None:
        self.hp -= damage
        self.hit_flash_timer = 0.15
        self.size_scale = 1.25

    def update_animation(self, dt: float) -> None:
        if self.hit_flash_timer > 0:
            self.hit_flash_timer -= dt
            if self.size_scale > 1.0:
                self.size_scale -= dt * 5.0
                if self.size_scale < 1.0:
                    self.size_scale = 1.0
        else:
            self.size_scale = 1.0

    @property
    def current_radius(self) -> float:
        return self.radius * self.size_scale


class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = 640.0
        self.y = 360.0
        self.radius = 16.0
        self.max_hp = 150.0
        self.hp = 150.0
        self.regen = 2.5
        self.armor_reduction = 0.05
        self.move_speed = 240.0
        self.damage_multiplier = 1.0
        self.attack_speed_multiplier = 1.0
        self.projectile_speed_multiplier = 1.0
        self.projectile_size_multiplier = 1.0
        self.magnet_radius = 105.0
        self.shot_cooldown = 0.2
        self.triple_cooldown = 0.8
        self.pulse_cooldown = 1.2
        self.lance_cooldown = 0.6
        self.lightning_cooldown = 1.1
        self.saw_cooldown = 0.7
        self.aura_tick_cooldown = 0.2
        self.aura_radius = 82.0
        self.flat_damage_bonus = 0.0
        self.multishot_multiplier = 0.0
        self.frost_cooldown = 0.8
        self.toxic_cooldown = 0.5
        self.flame_cooldown = 0.6
        self.poison_regen_multiplier = 1.0
        self.shield_points = 0.0
        self.temp_damage_boost = 0.0
        self.level = 1
        self.xp = 0
        self.xp_to_next = 8

    def heal(self, dt: float) -> None:
        self.hp = min(self.max_hp, self.hp + self.regen * self.poison_regen_multiplier * dt)

    def update_movement(self, dt: float, up: bool, down: bool, left: bool, right: bool) -> None:
        dx = dy = 0.0
        if up:
            dy -= 1
        if down:
            dy += 1
        if left:
            dx -= 1
        if right:
            dx += 1
        if dx == 0 and dy == 0:
            return
        length = math.hypot(dx, dy)
        self.x += (dx / length) * self.move_speed * dt
        self.y += (dy / length) * self.move_speed * dt
        self.x = clamp(self.x, self.radius, WIDTH - self.radius)
        self.y = clamp(self.y, self.radius, HEIGHT - self.radius)


@dataclass
class SaveData:
    high_score: int = 0
    best_multi_kill: int = 0
    best_no_damage_seconds: float = 0.0
    total_coins: int = 0
    saved_run_coins: int = 0
    saved_score: int = 0
    saved_wave: int = 1
    saved_world_time: float = 0.0
    saved_character: str = "Astra"
    unlocked_characters: list = field(default_factory=lambda: ["Astra"])


class SaveSystem:
    def load(self) -> SaveData:
        if not SAVE_FILE.exists():
            return SaveData()
        try:
            with open(SAVE_FILE, encoding="utf-8") as f:
                raw = json.load(f)
            return SaveData(
                high_score=raw.get("high_score", 0),
                best_multi_kill=raw.get("best_multi_kill", 0),
                best_no_damage_seconds=raw.get("best_no_damage_seconds", 0.0),
                total_coins=raw.get("total_coins", 0),
                saved_run_coins=raw.get("saved_run_coins", 0),
                saved_score=raw.get("saved_score", 0),
                saved_wave=raw.get("saved_wave", 1),
                saved_world_time=raw.get("saved_world_time", 0.0),
                saved_character=raw.get("saved_character", "Astra"),
                unlocked_characters=raw.get("unlocked_characters", ["Astra"]),
            )
        except (OSError, json.JSONDecodeError, TypeError):
            return SaveData()

    def save(self, data: SaveData) -> None:
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "high_score": data.high_score,
                        "best_multi_kill": data.best_multi_kill,
                        "best_no_damage_seconds": data.best_no_damage_seconds,
                        "total_coins": data.total_coins,
                        "saved_run_coins": data.saved_run_coins,
                        "saved_score": data.saved_score,
                        "saved_wave": data.saved_wave,
                        "saved_world_time": data.saved_world_time,
                        "saved_character": data.saved_character,
                        "unlocked_characters": list(data.unlocked_characters),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError:
            pass


class Game:
    def __init__(self):
        ensure_assets()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Java Survivors — Diabloid")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Segoe UI", 17, bold=True)
        self.font_small = pygame.font.SysFont("Segoe UI", 14)
        self.font_label = pygame.font.SysFont("Segoe UI", 13, bold=True)
        self.font_big = pygame.font.SysFont("Segoe UI", 40, bold=True)
        self.font_huge = pygame.font.SysFont("Segoe UI", 56, bold=True)
        self.font_mid = pygame.font.SysFont("Segoe UI", 26)
        self.font_menu = pygame.font.SysFont("Segoe UI", 22)
        self.font_title = pygame.font.SysFont("Segoe UI", 18, bold=True)

        self.rng = random.Random()
        self.save_system = SaveSystem()
        self.save_data = self.save_system.load()

        self.images_loaded = False
        self.player_sprite: Optional[pygame.Surface] = None
        self.enemy_normal_sprite: Optional[pygame.Surface] = None
        self.enemy_tank_sprite: Optional[pygame.Surface] = None
        self.bg_sprite: Optional[pygame.Surface] = None
        self.load_assets()

        self.running = True
        self.up = self.down = self.left = self.right = False
        self.is_dashing = False
        self.dash_timer = 0.0
        self.dash_cooldown_timer = 0.0

        self.game_state = GameState.MENU
        self.upgrade_state = UpgradeState.NONE
        self.player = Player()
        self.enemies: list[Enemy] = []
        self.projectiles: list[Projectile] = []
        self.xp_orbs: list[XpOrb] = []
        self.damage_numbers: list[DamageNumber] = []
        self.player_effects: list[StatusEffect] = []
        self.particles: list[Particle] = []
        self.upgrade_choices: list[str] = []
        self.shop_choices: list[str] = []
        self.unlocked_weapons: set[WeaponType] = set()
        self.permanent_shop_upgrades: set[str] = set()
        self.branch_upgrades: dict[PerkBranch, list[str]] = {}
        self.extra_weapon_cooldowns: dict[WeaponType, float] = {}
        self.chain_lightnings: list[LightningEffect] = []
        self.saw_blades: list[SawBladeEffect] = []
        self.map_coins: list[CoinPickup] = []

        self.world_time = 0.0
        self.spawn_timer = 0.0
        self.contact_damage_timer = 0.0
        self.score = 0
        self.pending_level_ups = 0
        self.wave = 1
        self.wave_timer = 0.0
        self.boss_timer = 180.0
        self.shot_kill_streak = 0
        self.no_damage_time = 0.0
        self.selected_menu_action = 0
        self.selected_character_idx = 0
        self.character_select_active = False
        self.run_coins = 0
        self.coin_spawn_timer = 5.0
        self.footstep_timer = 0.0

        self.characters: list[CharacterDef] = []
        self.init_branch_upgrade_pools()
        self.init_characters()

    def load_assets(self) -> None:
        def load(path: Path) -> Optional[pygame.Surface]:
            if not path.exists():
                return None
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                return None

        bg_path = ASSETS_DIR / "background.jpg"
        self.player_sprite = load(ASSETS_DIR / "player.png")
        self.enemy_normal_sprite = load(ASSETS_DIR / "enemy_normal.png")
        self.enemy_tank_sprite = load(ASSETS_DIR / "enemy_tank.png")
        if bg_path.exists():
            try:
                self.bg_sprite = pygame.image.load(str(bg_path)).convert()
            except pygame.error:
                self.bg_sprite = None
        self.images_loaded = any(
            s is not None for s in (self.player_sprite, self.enemy_normal_sprite, self.enemy_tank_sprite, self.bg_sprite)
        )

    def init_branch_upgrade_pools(self) -> None:
        self.branch_upgrades = {
            PerkBranch.ATTACK: [
                "Сила +20%",
                "Скорость атаки +20%",
                "Урон +5",
                "Кол-во снарядов +1",
                "Оружие: Ледяная волна",
                "Оружие: Токсичный дротик",
                "Оружие: Огненный шар",
            ],
            PerkBranch.DEFENSE: ["Макс. HP +20", "Броня +8%", "Щит +30", "Регенерация +0.5"],
            PerkBranch.SUPPORT: [
                "Скорость движения +15%",
                "Магнит +20%",
                "Скорость снаряда +20%",
                "Размер снаряда +20%",
            ],
        }

    def init_characters(self) -> None:
        if self.characters:
            return
        self.characters = [
            CharacterDef("Astra", 0, WeaponType.MAGIC_BOLT, 1.0, 1.0),
            CharacterDef("Vulcan", 100, WeaponType.FLAME_ORB, 1.12, 0.95),
            CharacterDef("Glacia", 250, WeaponType.FROST_NOVA, 1.0, 1.08),
            CharacterDef("Venom", 500, WeaponType.TOXIC_DART, 0.95, 1.15),
            CharacterDef("Storm", 900, WeaponType.CHAIN_LIGHTNING, 1.10, 1.0),
            CharacterDef("Blade", 1400, WeaponType.SAW_BLADE, 1.18, 0.92),
            CharacterDef("Titan", 2200, WeaponType.PIERCE_LANCE, 1.25, 0.82),
            CharacterDef("Aura", 3400, WeaponType.DAMAGE_AURA, 0.9, 1.2),
            CharacterDef("Pulse", 5500, WeaponType.PULSE_RING, 1.05, 1.05),
            CharacterDef("Oracle", 10000, WeaponType.TRIPLE_CAST, 1.15, 1.12),
        ]
        if not self.save_data.unlocked_characters:
            self.save_data.unlocked_characters = ["Astra"]

    # --- particles ---
    def spawn_kill_explosion(self, x: float, y: float) -> None:
        for i in range(18):
            angle = self.rng.random() * math.tau
            speed = 60 + self.rng.random() * 180
            c = (255, 120, 80) if i % 2 == 0 else (255, 220, 110)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, 3 + self.rng.random() * 4, 0.5 + self.rng.random() * 0.5, c, i % 2 == 0)
            )

    def spawn_projectile_hit_sparks(self, x: float, y: float) -> None:
        for _ in range(8):
            angle = self.rng.random() * math.tau
            speed = 80 + self.rng.random() * 140
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, 2 + self.rng.random() * 2, 0.2 + self.rng.random() * 0.25, (255, 240, 140), True)
            )

    def spawn_footsteps(self, dt: float) -> None:
        self.footstep_timer -= dt
        if not (self.up or self.down or self.left or self.right) or self.footstep_timer > 0:
            return
        self.footstep_timer = 0.05
        self.particles.append(
            Particle(
                self.player.x + self.rng.random() * 8 - 4,
                self.player.y + self.rng.random() * 8 - 4,
                self.rng.random() * 12 - 6,
                self.rng.random() * 12 - 6,
                2.5,
                0.25,
                (120, 220, 150),
                True,
            )
        )

    def update_particles(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.95
            p.vy *= 0.95
            if p.life > 0:
                alive.append(p)
        self.particles = alive

    def draw_particles(self) -> None:
        for p in self.particles:
            alpha = max(0, int((p.life / p.max_life) * 255))
            color = (*p.color[:3], alpha)
            surf = pygame.Surface((int(p.size), int(p.size)), pygame.SRCALPHA)
            if p.circle:
                pygame.draw.circle(surf, color, (int(p.size / 2), int(p.size / 2)), int(p.size / 2))
            else:
                surf.fill(color)
            self.screen.blit(surf, (int(p.x - p.size / 2), int(p.y - p.size / 2)))

    # --- game loop ---
    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.033)
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.on_key_down(event.key)
            elif event.type == pygame.KEYUP:
                self.on_key_up(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.on_mouse_click(event.pos)

    def on_key_down(self, key: int) -> None:
        if key in (pygame.K_w, pygame.K_UP):
            self.up = True
        if key in (pygame.K_s, pygame.K_DOWN):
            self.down = True
        if key in (pygame.K_a, pygame.K_LEFT):
            self.left = True
        if key in (pygame.K_d, pygame.K_RIGHT):
            self.right = True

        if key == pygame.K_RETURN:
            if self.game_state in (GameState.MENU, GameState.GAME_OVER):
                self.handle_menu_confirm()

        if self.game_state == GameState.MENU:
            if not self.character_select_active:
                if key in (pygame.K_UP, pygame.K_w):
                    self.selected_menu_action = max(0, self.selected_menu_action - 1)
                if key in (pygame.K_DOWN, pygame.K_s):
                    self.selected_menu_action = min(1, self.selected_menu_action + 1)
            else:
                if key in (pygame.K_UP, pygame.K_w):
                    self.selected_character_idx = max(0, self.selected_character_idx - 1)
                if key in (pygame.K_DOWN, pygame.K_s):
                    self.selected_character_idx = min(len(self.characters) - 1, self.selected_character_idx + 1)
                if pygame.K_1 <= key <= pygame.K_9:
                    self.selected_character_idx = min(len(self.characters) - 1, key - pygame.K_1)
                if key == pygame.K_0:
                    self.selected_character_idx = min(9, len(self.characters) - 1)

        if key == pygame.K_SPACE and not self.is_dashing and self.dash_cooldown_timer <= 0 and self.game_state == GameState.PLAYING:
            self.perform_dash()

        if self.upgrade_state == UpgradeState.PAUSED_FOR_UPGRADE:
            if key == pygame.K_1:
                self.apply_upgrade(0)
            elif key == pygame.K_2:
                self.apply_upgrade(1)
            elif key == pygame.K_3:
                self.apply_upgrade(2)

        if self.upgrade_state == UpgradeState.PAUSED_FOR_SHOP:
            if key == pygame.K_1:
                self.apply_shop_choice(0)
            elif key == pygame.K_2:
                self.apply_shop_choice(1)
            elif key == pygame.K_3:
                self.apply_shop_choice(2)
            elif key == pygame.K_ESCAPE:
                self.upgrade_state = UpgradeState.NONE
                self.shop_choices.clear()

    def on_key_up(self, key: int) -> None:
        if key in (pygame.K_w, pygame.K_UP):
            self.up = False
        if key in (pygame.K_s, pygame.K_DOWN):
            self.down = False
        if key in (pygame.K_a, pygame.K_LEFT):
            self.left = False
        if key in (pygame.K_d, pygame.K_RIGHT):
            self.right = False

    def on_mouse_click(self, pos: tuple[int, int]) -> None:
        mx, my = pos
        if self.upgrade_state == UpgradeState.PAUSED_FOR_UPGRADE:
            cx = WIDTH // 2
            left = cx - UPGRADE_CARD_W // 2
            for i in range(len(self.upgrade_choices)):
                top = UPGRADE_START_Y + i * (UPGRADE_CARD_H + UPGRADE_CARD_GAP)
                if left <= mx <= left + UPGRADE_CARD_W and top <= my <= top + UPGRADE_CARD_H:
                    self.apply_upgrade(i)
                    break
        if self.upgrade_state == UpgradeState.PAUSED_FOR_SHOP:
            cx = WIDTH // 2
            left = cx - SHOP_CARD_W // 2
            for i in range(len(self.shop_choices)):
                top = SHOP_START_Y + i * (SHOP_CARD_H + SHOP_CARD_GAP)
                if left <= mx <= left + SHOP_CARD_W and top <= my <= top + SHOP_CARD_H:
                    self.apply_shop_choice(i)
                    break

    def perform_dash(self) -> None:
        self.is_dashing = True
        self.dash_timer = DASH_DURATION
        self.dash_cooldown_timer = DASH_COOLDOWN
        dx = dy = 0.0
        if self.up:
            dy -= 1
        if self.down:
            dy += 1
        if self.left:
            dx -= 1
        if self.right:
            dx += 1
        if dx == 0 and dy == 0:
            dy = -1
        length = math.hypot(dx, dy)
        if length > 0:
            self.player.x += (dx / length) * self.player.move_speed * DASH_SPEED_MULTIPLIER * DASH_DURATION
            self.player.y += (dy / length) * self.player.move_speed * DASH_SPEED_MULTIPLIER * DASH_DURATION
            self.player.x = clamp(self.player.x, self.player.radius, WIDTH - self.player.radius)
            self.player.y = clamp(self.player.y, self.player.radius, HEIGHT - self.player.radius)

    def update(self, dt: float) -> None:
        if self.game_state in (GameState.MENU, GameState.GAME_OVER) or self.upgrade_state in (
            UpgradeState.PAUSED_FOR_UPGRADE,
            UpgradeState.PAUSED_FOR_SHOP,
        ):
            return

        self.world_time += dt
        self.wave_timer += dt
        self.no_damage_time += dt
        self.save_data.best_no_damage_seconds = max(self.save_data.best_no_damage_seconds, self.no_damage_time)
        self.update_wave_progress()

        if self.is_dashing:
            self.dash_timer -= dt
            if self.dash_timer <= 0:
                self.is_dashing = False
        else:
            self.dash_cooldown_timer -= dt

        self.player.heal(dt)
        self.player.update_movement(dt, self.up, self.down, self.left, self.right)
        self.update_player_status_effects(dt)
        self.spawn_footsteps(dt)
        self.update_particles(dt)
        self.update_enemy_status_effects(dt)
        self.update_chain_lightning(dt)
        self.update_saw_blades(dt)
        self.update_weapons(dt)
        self.spawn_enemies(dt)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_xp_orbs(dt)
        self.update_coins(dt)
        self.update_damage_numbers(dt)

    def update_wave_progress(self) -> None:
        self.boss_timer -= 1.0 / 120.0
        if self.boss_timer <= 0:
            self.boss_timer = 180.0
            self.enemies.append(self.spawn_boss())
        if self.wave_timer >= 30.0:
            self.wave_timer = 0.0
            self.wave += 1
            if self.wave % 3 == 0:
                self.roll_shop_choices()
                self.upgrade_state = UpgradeState.PAUSED_FOR_SHOP

    def spawn_boss(self) -> Enemy:
        boss = Enemy(WIDTH * 0.5, -80, 38, 1800 + self.wave * 120, 68, 14 + self.wave * 1.2, 45)
        boss.kind = EnemyKind.BOSS
        boss.score = 600 + self.wave * 40
        return boss

    def update_coins(self, dt: float) -> None:
        self.coin_spawn_timer -= dt
        if self.coin_spawn_timer <= 0:
            self.coin_spawn_timer = 4.0 + self.rng.random() * 4.0
            self.map_coins.append(
                CoinPickup(30 + self.rng.random() * (WIDTH - 60), 30 + self.rng.random() * (HEIGHT - 60), 1 + self.rng.randint(0, 3))
            )
        remaining = []
        for c in self.map_coins:
            if distance_sq(c.x, c.y, self.player.x, self.player.y) <= (self.player.radius + 8) ** 2:
                self.run_coins += c.value
                self.save_data.total_coins += c.value
            else:
                remaining.append(c)
        self.map_coins = remaining

    def total_damage_multiplier(self) -> float:
        return self.player.damage_multiplier * (1.0 + self.player.temp_damage_boost)

    def find_nearest_enemy(self) -> Optional[Enemy]:
        if not self.enemies:
            return None
        return min(self.enemies, key=lambda e: distance_sq(self.player.x, self.player.y, e.x, e.y))

    def projectile_towards(self, target: Enemy, base_damage: float, base_radius: float, base_speed: float, pierce: int) -> Optional[Projectile]:
        dx, dy = target.x - self.player.x, target.y - self.player.y
        length = math.hypot(dx, dy)
        if length < 0.001:
            return None
        speed = base_speed * self.player.projectile_speed_multiplier
        radius = base_radius * self.player.projectile_size_multiplier
        damage = base_damage * self.total_damage_multiplier() + self.player.flat_damage_bonus
        return Projectile(
            self.player.x,
            self.player.y,
            (dx / length) * speed,
            (dy / length) * speed,
            damage,
            radius,
            pierce,
        )

    def spawn_projectile_towards(self, target: Enemy, base_damage: float, base_radius: float, base_speed: float, pierce: int) -> None:
        p = self.projectile_towards(target, base_damage, base_radius, base_speed, pierce)
        if p:
            self.projectiles.append(p)

    def is_extra_weapon(self, weapon: WeaponType) -> bool:
        order = list(WeaponType)
        return order.index(weapon) >= order.index(EXTRA_WEAPON_START)

    def update_weapons(self, dt: float) -> None:
        if not self.enemies:
            return
        p = self.player
        if WeaponType.MAGIC_BOLT in self.unlocked_weapons:
            p.shot_cooldown -= dt
            if p.shot_cooldown <= 0:
                self.shoot_magic_bolt()
                p.shot_cooldown = max(0.08, 0.45 / p.attack_speed_multiplier)
        if WeaponType.TRIPLE_CAST in self.unlocked_weapons:
            p.triple_cooldown -= dt
            if p.triple_cooldown <= 0:
                self.shoot_triple_cast()
                p.triple_cooldown = max(0.20, 1.10 / p.attack_speed_multiplier)
        if WeaponType.PULSE_RING in self.unlocked_weapons:
            p.pulse_cooldown -= dt
            if p.pulse_cooldown <= 0:
                self.shoot_pulse_ring()
                p.pulse_cooldown = max(0.50, 2.20 / p.attack_speed_multiplier)
        if WeaponType.PIERCE_LANCE in self.unlocked_weapons:
            p.lance_cooldown -= dt
            if p.lance_cooldown <= 0:
                self.shoot_pierce_lance()
                p.lance_cooldown = max(0.16, 0.95 / p.attack_speed_multiplier)
        if WeaponType.DAMAGE_AURA in self.unlocked_weapons:
            self.update_damage_aura(dt)
        if WeaponType.CHAIN_LIGHTNING in self.unlocked_weapons:
            p.lightning_cooldown -= dt
            if p.lightning_cooldown <= 0:
                self.cast_chain_lightning()
                p.lightning_cooldown = max(0.25, 1.70 / p.attack_speed_multiplier)
        if WeaponType.SAW_BLADE in self.unlocked_weapons:
            p.saw_cooldown -= dt
            if p.saw_cooldown <= 0:
                self.shoot_saw_blade()
                p.saw_cooldown = max(0.20, 1.35 / p.attack_speed_multiplier)
        if WeaponType.FROST_NOVA in self.unlocked_weapons:
            p.frost_cooldown -= dt
            if p.frost_cooldown <= 0:
                self.shoot_frost_nova()
                p.frost_cooldown = max(0.25, 2.10 / p.attack_speed_multiplier)
        if WeaponType.TOXIC_DART in self.unlocked_weapons:
            p.toxic_cooldown -= dt
            if p.toxic_cooldown <= 0:
                self.shoot_toxic_dart()
                p.toxic_cooldown = max(0.14, 0.72 / p.attack_speed_multiplier)
        if WeaponType.FLAME_ORB in self.unlocked_weapons:
            p.flame_cooldown -= dt
            if p.flame_cooldown <= 0:
                self.shoot_flame_orb()
                p.flame_cooldown = max(0.18, 0.95 / p.attack_speed_multiplier)
        self.update_extra_weapons(dt)

    def update_extra_weapons(self, dt: float) -> None:
        for weapon in list(self.unlocked_weapons):
            if not self.is_extra_weapon(weapon):
                continue
            cd = self.extra_weapon_cooldowns.get(weapon, 0.1) - dt
            if cd <= 0:
                self.fire_extra_weapon(weapon)
                cd = max(0.20, 1.35 / self.player.attack_speed_multiplier)
            self.extra_weapon_cooldowns[weapon] = cd

    def fire_extra_weapon(self, weapon: WeaponType) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        p = self.projectile_towards(target, 13.5, 5.5, 560.0, 1)
        if p is None:
            return
        if weapon in (WeaponType.FIRE_WAVE, WeaponType.FIRE_LANCE, WeaponType.FIRE_METEOR):
            p.applies_burn = True
        elif weapon in (WeaponType.ICE_SHARD, WeaponType.ICE_SPIKE, WeaponType.ICE_STORM):
            p.applies_slow = True
        elif weapon in (WeaponType.WATER_JET, WeaponType.WATER_ORB, WeaponType.WATER_TIDE):
            p.life = 2.4
        elif weapon in (WeaponType.EARTH_SPIKE, WeaponType.EARTH_QUAKE, WeaponType.EARTH_BLADE):
            p.radius *= 1.35
        elif weapon in (WeaponType.THUNDER_SPEAR, WeaponType.THUNDER_FIELD):
            p.damage *= 1.20
        elif weapon == WeaponType.SHADOW_SCYTHE:
            p.pierce = 3
        self.projectiles.append(p)

    def shoot_magic_bolt(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        total_shots = max(1, int(round(1 + self.player.multishot_multiplier)))
        if total_shots > 1:
            dx, dy = target.x - self.player.x, target.y - self.player.y
            length = math.hypot(dx, dy)
            if length < 0.001:
                return
            base_angle = math.atan2(dy, dx)
            spread, step = 0.3, 0.3 / max(1, total_shots - 1)
            for i in range(total_shots):
                angle = base_angle + (i - (total_shots - 1) / 2.0) * step
                speed = 600.0 * self.player.projectile_speed_multiplier
                self.projectiles.append(
                    Projectile(
                        self.player.x,
                        self.player.y,
                        math.cos(angle) * speed,
                        math.sin(angle) * speed,
                        18.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                        6.0 * self.player.projectile_size_multiplier,
                        0,
                    )
                )
        else:
            self.spawn_projectile_towards(target, 18.0, 6.0, 600.0, 0)

    def shoot_triple_cast(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        dx, dy = target.x - self.player.x, target.y - self.player.y
        base_angle = math.atan2(dy, dx)
        total_shots = max(3, int(round(3 + self.player.multishot_multiplier)))
        spread, step = 0.44, 0.44 / max(1, total_shots - 1)
        for i in range(total_shots):
            angle = base_angle + (i - (total_shots - 1) / 2.0) * step
            speed = 540.0 * self.player.projectile_speed_multiplier
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    12.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                    5.5 * self.player.projectile_size_multiplier,
                    0,
                )
            )

    def shoot_pulse_ring(self) -> None:
        self.shot_kill_streak = 0
        total = max(10, int(round(10 + self.player.multishot_multiplier)))
        for i in range(total):
            angle = (math.tau / total) * i
            speed = 430.0 * self.player.projectile_speed_multiplier
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    14.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                    5.0 * self.player.projectile_size_multiplier,
                    0,
                )
            )

    def shoot_pierce_lance(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        dx, dy = target.x - self.player.x, target.y - self.player.y
        length = math.hypot(dx, dy)
        if length < 0.001:
            return
        base_angle = math.atan2(dy, dx)
        total_shots = max(1, int(round(1 + self.player.multishot_multiplier)))
        step = 0.2 / max(1, total_shots - 1)
        for i in range(total_shots):
            angle = base_angle + (i - (total_shots - 1) / 2.0) * step
            speed = 760.0 * self.player.projectile_speed_multiplier
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    24.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                    7.0 * self.player.projectile_size_multiplier,
                    2,
                )
            )

    def update_damage_aura(self, dt: float) -> None:
        self.player.aura_tick_cooldown -= dt
        if self.player.aura_tick_cooldown > 0:
            return
        self.player.aura_tick_cooldown = 0.28
        aura_radius = self.player.aura_radius * self.player.projectile_size_multiplier
        aura_damage = 7.5 * self.total_damage_multiplier() + self.player.flat_damage_bonus * 0.6
        for enemy in list(self.enemies):
            if distance_sq(self.player.x, self.player.y, enemy.x, enemy.y) <= aura_radius * aura_radius:
                self.damage_enemy(enemy, aura_damage)

    def cast_chain_lightning(self) -> None:
        self.shot_kill_streak = 0
        first = self.find_nearest_enemy()
        if first is None:
            return
        second = third = None
        chain_range_sq = 210 * 210
        for enemy in self.enemies:
            if enemy is first:
                continue
            if distance_sq(first.x, first.y, enemy.x, enemy.y) <= chain_range_sq:
                second = enemy
                break
        if second:
            for enemy in self.enemies:
                if enemy in (first, second):
                    continue
                if distance_sq(second.x, second.y, enemy.x, enemy.y) <= chain_range_sq:
                    third = enemy
                    break
        self.chain_lightnings.append(LightningEffect(first, second, third))
        base = 26.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus
        self.damage_enemy(first, base)
        if second:
            self.damage_enemy(second, base * 0.72)
        if third:
            self.damage_enemy(third, base * 0.5)

    def update_chain_lightning(self, dt: float) -> None:
        alive = []
        for le in self.chain_lightnings:
            le.life -= dt
            if le.life > 0:
                alive.append(le)
        self.chain_lightnings = alive

    def shoot_saw_blade(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        dx, dy = target.x - self.player.x, target.y - self.player.y
        base_angle = math.atan2(dy, dx)
        total_shots = max(1, int(round(1 + self.player.multishot_multiplier)))
        step = 0.5 / max(1, total_shots - 1)
        for i in range(total_shots):
            angle = base_angle + (i - (total_shots - 1) / 2.0) * step
            self.saw_blades.append(
                SawBladeEffect(
                    self.player.x,
                    self.player.y,
                    angle,
                    500.0 * self.player.projectile_speed_multiplier,
                    8.0 * self.player.projectile_size_multiplier,
                    20.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                    5,
                )
            )

    def update_saw_blades(self, dt: float) -> None:
        current_enemies = list(self.enemies)
        alive = []
        for sb in self.saw_blades:
            sb.life -= dt
            sb.angle += dt * 15.0
            sb.x += math.cos(sb.angle) * sb.speed * dt
            sb.y += math.sin(sb.angle) * sb.speed * dt
            for e in current_enemies:
                if e.hp <= 0:
                    continue
                if distance_sq(sb.x, sb.y, e.x, e.y) <= (sb.radius + e.radius) ** 2:
                    self.damage_enemy(e, sb.damage)
                    sb.pierce -= 1
            if sb.life <= 0 or sb.pierce <= 0 or sb.x < -100 or sb.y < -100 or sb.x > WIDTH + 100 or sb.y > HEIGHT + 100:
                continue
            alive.append(sb)
        self.saw_blades = alive

    def shoot_frost_nova(self) -> None:
        self.shot_kill_streak = 0
        for i in range(12):
            angle = (math.tau / 12) * i
            speed = 360.0 * self.player.projectile_speed_multiplier
            p = Projectile(
                self.player.x,
                self.player.y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                10.0 * self.total_damage_multiplier() + self.player.flat_damage_bonus,
                5.2 * self.player.projectile_size_multiplier,
                0,
                life=0.85,
                applies_slow=True,
            )
            self.projectiles.append(p)

    def shoot_toxic_dart(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        p = self.projectile_towards(target, 11.0, 4.5, 760.0, 1)
        if p:
            p.applies_poison = True
            self.projectiles.append(p)

    def shoot_flame_orb(self) -> None:
        self.shot_kill_streak = 0
        target = self.find_nearest_enemy()
        if target is None:
            return
        p = self.projectile_towards(target, 16.0, 6.8, 520.0, 0)
        if p:
            p.applies_burn = True
            p.life = 2.2
            self.projectiles.append(p)

    def spawn_enemies(self, dt: float) -> None:
        self.spawn_timer -= dt
        if self.spawn_timer > 0:
            return
        t = self.world_time
        difficulty = 1.0 + (t * 0.018) + (t ** 1.18) * 0.0012
        batch = 1 + int(t // 45) + (1 if self.rng.random() < min(0.55, 0.20 + t / 260) else 0)
        self.spawn_timer = max(0.08, 0.78 - t * 0.0038)
        for _ in range(batch):
            self.enemies.append(self.spawn_enemy(difficulty))

    def spawn_enemy(self, difficulty: float) -> Enemy:
        roll = self.rng.random()
        side = self.rng.random()
        if side < 0.25:
            x, y = -50, self.rng.random() * HEIGHT
        elif side < 0.5:
            x, y = WIDTH + 50, self.rng.random() * HEIGHT
        elif side < 0.75:
            x, y = self.rng.random() * WIDTH, -50
        else:
            x, y = self.rng.random() * WIDTH, HEIGHT + 50

        if roll < 0.12:
            e = Enemy(x, y, 10, 26 * difficulty, 190 + difficulty * 14, 8 + difficulty * 1.8, 2 + int(difficulty * 0.7))
            e.kind = EnemyKind.SPEEDER
        elif roll < 0.26:
            e = Enemy(x, y, 18, 55 * difficulty, 92 + difficulty * 8, 4.2 + difficulty * 1.4, 3 + int(difficulty * 0.9))
            e.kind = EnemyKind.SHOOTER
        elif roll < 0.48:
            e = Enemy(x, y, 22, 95 * difficulty, 62 + difficulty * 5, 5 + difficulty * 2, 4 + int(difficulty))
            e.kind = EnemyKind.TANK
        else:
            e = Enemy(x, y, 14, 40 * difficulty, 105 + difficulty * 8, 3 + difficulty, 2 + int(difficulty * 0.8))
            e.kind = EnemyKind.NORMAL
        e.score = e.xp_value * 3
        return e

    def update_enemies(self, dt: float) -> None:
        for e in self.enemies:
            e.attack_cooldown -= dt
            if e.kind == EnemyKind.BOSS:
                if e.hp < 1200:
                    e.phase = 2
                if e.hp < 600:
                    e.phase = 3
                if e.attack_cooldown <= 0:
                    if e.phase == 1:
                        for i in range(18):
                            a = (math.tau / 18) * i
                            ep = Projectile(e.x, e.y, math.cos(a) * 260, math.sin(a) * 260, 9 + self.wave * 0.6, 4, 0, from_enemy=True)
                            self.projectiles.append(ep)
                        e.attack_cooldown = 4.0
                    elif e.phase == 2:
                        self.enemies.append(self.spawn_enemy(1.0 + self.world_time * 0.01))
                        self.enemies.append(self.spawn_enemy(1.0 + self.world_time * 0.01))
                        e.attack_cooldown = 5.5
                    else:
                        for _ in range(4):
                            self.enemies.append(self.spawn_enemy(1.1 + self.world_time * 0.012))
                        e.attack_cooldown = 6.0

            dx, dy = self.player.x - e.x, self.player.y - e.y
            length = math.hypot(dx, dy)
            if length > 0.0001 and e.kind != EnemyKind.SHOOTER:
                e.x += (dx / length) * e.speed * e.speed_multiplier * dt
                e.y += (dy / length) * e.speed * e.speed_multiplier * dt
            elif e.kind == EnemyKind.SHOOTER:
                preferred = 180
                if length > preferred + 20:
                    e.x += (dx / length) * e.speed * 0.75 * dt
                    e.y += (dy / length) * e.speed * 0.75 * dt
                elif length < preferred - 20 and length > 0.0001:
                    e.x -= (dx / length) * e.speed * 0.75 * dt
                    e.y -= (dy / length) * e.speed * 0.75 * dt
                if e.attack_cooldown <= 0 and length > 50:
                    ep = Projectile(e.x, e.y, (dx / length) * 300, (dy / length) * 300, 7.0 + self.wave * 0.3, 3.0, 0, from_enemy=True)
                    self.projectiles.append(ep)
                    e.attack_cooldown = 1.3
            e.update_animation(dt)
            if distance_sq(e.x, e.y, self.player.x, self.player.y) <= (e.radius + self.player.radius + 14) ** 2:
                e.attack_windup = min(1.0, e.attack_windup + dt * 3.5)
            else:
                e.attack_windup = max(0.0, e.attack_windup - dt * 2.0)

        self.contact_damage_timer -= dt
        if self.contact_damage_timer <= 0:
            total = 0.0
            for e in self.enemies:
                if not self.is_dashing and distance_sq(e.x, e.y, self.player.x, self.player.y) <= (e.radius + self.player.radius) ** 2:
                    total += e.contact_damage
            if total > 0:
                incoming = total * (1.0 - self.player.armor_reduction)
                incoming = self.absorb_shield_damage(incoming)
                self.player.hp -= incoming
                self.no_damage_time = 0
                if self.player.hp <= 0:
                    self.player.hp = 0
                    self.game_over()
            self.contact_damage_timer = CONTACT_DAMAGE_TICK

    def game_over(self) -> None:
        self.game_state = GameState.GAME_OVER
        self.save_data.best_no_damage_seconds = max(self.save_data.best_no_damage_seconds, self.no_damage_time)
        self.save_data.saved_run_coins = self.run_coins
        self.save_data.saved_score = self.score
        self.save_data.saved_wave = self.wave
        self.save_data.saved_world_time = self.world_time
        self.save_system.save(self.save_data)

    def update_projectiles(self, dt: float) -> None:
        alive = []
        for p in self.projectiles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.life -= dt
            if p.life <= 0 or p.x < -100 or p.y < -100 or p.x > WIDTH + 100 or p.y > HEIGHT + 100:
                continue
            if p.from_enemy:
                if not self.is_dashing and distance_sq(p.x, p.y, self.player.x, self.player.y) <= (p.radius + self.player.radius) ** 2:
                    incoming = self.absorb_shield_damage(p.damage * (1.0 - self.player.armor_reduction))
                    self.player.hp -= incoming
                    self.no_damage_time = 0
                    self.spawn_projectile_hit_sparks(p.x, p.y)
                    if self.player.hp <= 0:
                        self.player.hp = 0
                        self.game_over()
                else:
                    alive.append(p)
                continue

            hit = None
            for e in self.enemies:
                if distance_sq(p.x, p.y, e.x, e.y) <= (p.radius + e.radius) ** 2:
                    hit = e
                    break
            if hit:
                self.damage_enemy(hit, p.damage)
                self.spawn_projectile_hit_sparks(p.x, p.y)
                if p.applies_slow:
                    self.add_enemy_status(hit, StatusEffect(StatusEffectType.SLOW, 2.5, 0.0, 0.45))
                if p.applies_burn:
                    self.add_enemy_status(hit, StatusEffect(StatusEffectType.BURN, 3.0, 7.0 * self.player.damage_multiplier, 0.0))
                if p.applies_poison:
                    self.add_player_status(StatusEffect(StatusEffectType.POISON, 3.5, 0.0, 0.5))
                if p.pierce > 0:
                    p.pierce -= 1
                    alive.append(p)
            else:
                alive.append(p)
        self.projectiles = alive

    def damage_enemy(self, enemy: Enemy, damage: float) -> None:
        enemy.take_damage(damage)
        self.damage_numbers.append(DamageNumber(enemy.x, enemy.y - enemy.radius, int(damage)))
        if enemy.hp <= 0:
            if enemy in self.enemies:
                self.enemies.remove(enemy)
            self.score += enemy.score
            self.xp_orbs.append(XpOrb(enemy.x, enemy.y, enemy.xp_value))
            self.shot_kill_streak += 1
            self.spawn_kill_explosion(enemy.x, enemy.y)
            self.save_data.best_multi_kill = max(self.save_data.best_multi_kill, self.shot_kill_streak)
            self.save_data.high_score = max(self.save_data.high_score, self.score)

    def update_xp_orbs(self, dt: float) -> None:
        remaining = []
        for orb in self.xp_orbs:
            dx, dy = self.player.x - orb.x, self.player.y - orb.y
            dist = math.hypot(dx, dy)
            if dist < self.player.magnet_radius and dist > 0.001:
                speed = 160 + (self.player.magnet_radius - min(self.player.magnet_radius, dist)) * 2.3
                orb.x += (dx / dist) * speed * dt
                orb.y += (dy / dist) * speed * dt
            if distance_sq(orb.x, orb.y, self.player.x, self.player.y) < (self.player.radius + 7) ** 2:
                self.player.xp += orb.value
                while self.player.xp >= self.player.xp_to_next:
                    self.player.xp -= self.player.xp_to_next
                    self.player.level += 1
                    self.player.xp_to_next = int(round(self.player.xp_to_next * 1.15 + 2))
                    self.pending_level_ups += 1
                if self.pending_level_ups > 0 and self.upgrade_state == UpgradeState.NONE:
                    self.roll_upgrade_choices()
                    self.upgrade_state = UpgradeState.PAUSED_FOR_UPGRADE
            else:
                remaining.append(orb)
        self.xp_orbs = remaining

    def update_damage_numbers(self, dt: float) -> None:
        alive = []
        for dn in self.damage_numbers:
            dn.y -= 15.0 * dt
            dn.alpha -= 2.0 * dt
            if dn.alpha > 0:
                alive.append(dn)
        self.damage_numbers = alive

    def roll_upgrade_choices(self) -> None:
        self.upgrade_choices.clear()
        for branch in PerkBranch:
            pool = list(self.branch_upgrades[branch])
            self.add_missing_weapons_to_pool(pool)
            if pool:
                self.upgrade_choices.append(f"{branch.value}: {self.rng.choice(pool)}")

    def add_missing_weapons_to_pool(self, pool: list[str]) -> None:
        unlocks = [
            (WeaponType.TRIPLE_CAST, "Оружие: Тройной залп"),
            (WeaponType.PULSE_RING, "Оружие: Кольцо импульса"),
            (WeaponType.PIERCE_LANCE, "Оружие: Пронзающее копье"),
            (WeaponType.DAMAGE_AURA, "Оружие: Аура боли"),
            (WeaponType.CHAIN_LIGHTNING, "Оружие: Цепная молния"),
            (WeaponType.SAW_BLADE, "Оружие: Пила"),
            (WeaponType.FIRE_WAVE, "Оружие: Огненная волна"),
            (WeaponType.FIRE_LANCE, "Оружие: Огненное копье"),
            (WeaponType.FIRE_METEOR, "Оружие: Метеор"),
            (WeaponType.ICE_SHARD, "Оружие: Ледяной осколок"),
            (WeaponType.ICE_SPIKE, "Оружие: Ледяной шип"),
            (WeaponType.ICE_STORM, "Оружие: Ледяной шторм"),
            (WeaponType.WATER_JET, "Оружие: Водяной поток"),
            (WeaponType.WATER_ORB, "Оружие: Водяная сфера"),
            (WeaponType.WATER_TIDE, "Оружие: Прилив"),
            (WeaponType.EARTH_SPIKE, "Оружие: Каменный шип"),
            (WeaponType.EARTH_QUAKE, "Оружие: Землетрясение"),
            (WeaponType.EARTH_BLADE, "Оружие: Земляной клинок"),
            (WeaponType.THUNDER_SPEAR, "Оружие: Громовое копье"),
            (WeaponType.THUNDER_FIELD, "Оружие: Грозовое поле"),
            (WeaponType.SHADOW_SCYTHE, "Оружие: Теневая коса"),
        ]
        for wt, label in unlocks:
            if wt not in self.unlocked_weapons:
                pool.append(label)

    def apply_upgrade(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.upgrade_choices):
            return
        picked = self.upgrade_choices[idx]
        for branch in PerkBranch:
            prefix = f"{branch.value}: "
            if picked.startswith(prefix):
                picked = picked[len(prefix) :]
                break
        p = self.player
        if picked.startswith("Сила"):
            p.damage_multiplier *= 1.20
        elif picked.startswith("Скорость атаки"):
            p.attack_speed_multiplier *= 1.20
        elif picked.startswith("Скорость движения"):
            p.move_speed *= 1.15
        elif picked.startswith("Макс. HP"):
            p.max_hp += 20
            p.hp = min(p.max_hp, p.hp + 20)
        elif picked.startswith("Регенерация"):
            p.regen += 0.5
        elif picked.startswith("Магнит"):
            p.magnet_radius *= 1.20
        elif picked.startswith("Броня"):
            p.armor_reduction = min(0.70, p.armor_reduction + 0.08)
        elif picked.startswith("Скорость снаряда"):
            p.projectile_speed_multiplier *= 1.20
        elif picked.startswith("Размер снаряда"):
            p.projectile_size_multiplier *= 1.20
        elif picked.startswith("Урон +5"):
            p.flat_damage_bonus += 5.0
        elif picked.startswith("Кол-во снарядов"):
            p.multishot_multiplier += 1.0
        elif picked.startswith("Щит +30"):
            self.add_player_status(StatusEffect(StatusEffectType.SHIELD, 12.0, 30.0, 0.0))
        elif "Тройной залп" in picked:
            self.unlocked_weapons.add(WeaponType.TRIPLE_CAST)
        elif "Кольцо импульса" in picked:
            self.unlocked_weapons.add(WeaponType.PULSE_RING)
        elif "Пронзающее копье" in picked:
            self.unlocked_weapons.add(WeaponType.PIERCE_LANCE)
        elif "Аура боли" in picked:
            self.unlocked_weapons.add(WeaponType.DAMAGE_AURA)
        elif "Цепная молния" in picked:
            self.unlocked_weapons.add(WeaponType.CHAIN_LIGHTNING)
        elif "Пила" in picked and "Оружие" in picked:
            self.unlocked_weapons.add(WeaponType.SAW_BLADE)
        elif "Ледяная волна" in picked:
            self.unlocked_weapons.add(WeaponType.FROST_NOVA)
        elif "Токсичный дротик" in picked:
            self.unlocked_weapons.add(WeaponType.TOXIC_DART)
        elif "Огненный шар" in picked:
            self.unlocked_weapons.add(WeaponType.FLAME_ORB)
        elif "Огненная волна" in picked:
            self.unlocked_weapons.add(WeaponType.FIRE_WAVE)
        elif "Огненное копье" in picked:
            self.unlocked_weapons.add(WeaponType.FIRE_LANCE)
        elif "Метеор" in picked:
            self.unlocked_weapons.add(WeaponType.FIRE_METEOR)
        elif "Ледяной осколок" in picked:
            self.unlocked_weapons.add(WeaponType.ICE_SHARD)
        elif "Ледяной шип" in picked:
            self.unlocked_weapons.add(WeaponType.ICE_SPIKE)
        elif "Ледяной шторм" in picked:
            self.unlocked_weapons.add(WeaponType.ICE_STORM)
        elif "Водяной поток" in picked:
            self.unlocked_weapons.add(WeaponType.WATER_JET)
        elif "Водяная сфера" in picked:
            self.unlocked_weapons.add(WeaponType.WATER_ORB)
        elif "Прилив" in picked:
            self.unlocked_weapons.add(WeaponType.WATER_TIDE)
        elif "Каменный шип" in picked:
            self.unlocked_weapons.add(WeaponType.EARTH_SPIKE)
        elif "Землетрясение" in picked:
            self.unlocked_weapons.add(WeaponType.EARTH_QUAKE)
        elif "Земляной клинок" in picked:
            self.unlocked_weapons.add(WeaponType.EARTH_BLADE)
        elif "Громовое копье" in picked:
            self.unlocked_weapons.add(WeaponType.THUNDER_SPEAR)
        elif "Грозовое поле" in picked:
            self.unlocked_weapons.add(WeaponType.THUNDER_FIELD)
        elif "Теневая коса" in picked:
            self.unlocked_weapons.add(WeaponType.SHADOW_SCYTHE)

        self.pending_level_ups -= 1
        if self.pending_level_ups > 0:
            self.roll_upgrade_choices()
        else:
            self.upgrade_state = UpgradeState.NONE
            self.upgrade_choices.clear()

    def roll_shop_choices(self) -> None:
        self.shop_choices = [
            "Временный бафф: Сила +35% (на 20с) [160 очков]",
            "Временный бафф: Щит +50 (на 15с) [180 очков]",
        ]
        if "PERM_REGEN" not in self.permanent_shop_upgrades:
            self.shop_choices.append("Постоянно: Регенерация +0.4 [300 очков]")
        else:
            self.shop_choices.append("Постоянно: Броня +4% [320 очков]")

    def apply_shop_choice(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.shop_choices):
            return
        choice = self.shop_choices[idx]
        cost = 300 if "[300" in choice else 320 if "[320" in choice else 180 if "[180" in choice else 160
        if self.score < cost:
            return
        self.score -= cost
        if "Сила" in choice:
            self.add_player_status(StatusEffect(StatusEffectType.TEMP_DAMAGE_BOOST, 20.0, 0.35, 0.0))
        elif "Щит" in choice:
            self.add_player_status(StatusEffect(StatusEffectType.SHIELD, 15.0, 50.0, 0.0))
        elif "Регенерация" in choice:
            self.permanent_shop_upgrades.add("PERM_REGEN")
            self.player.regen += 0.4
        elif "Броня" in choice:
            self.player.armor_reduction = min(0.80, self.player.armor_reduction + 0.04)
        self.upgrade_state = UpgradeState.NONE
        self.shop_choices.clear()

    def update_enemy_status_effects(self, dt: float) -> None:
        for enemy in list(self.enemies):
            enemy.speed_multiplier = 1.0
            alive_effects = []
            for effect in enemy.effects:
                effect.duration -= dt
                effect.tick_timer -= dt
                if effect.type == StatusEffectType.SLOW:
                    enemy.speed_multiplier = min(enemy.speed_multiplier, 1.0 - effect.modifier)
                elif effect.type == StatusEffectType.BURN and effect.tick_timer <= 0:
                    self.damage_enemy(enemy, effect.power)
                    effect.tick_timer = 0.5
                if effect.duration > 0:
                    alive_effects.append(effect)
            enemy.effects = alive_effects

    def update_player_status_effects(self, dt: float) -> None:
        self.player.temp_damage_boost = 0.0
        self.player.poison_regen_multiplier = 1.0
        self.player.shield_points = 0.0
        alive = []
        for effect in self.player_effects:
            effect.duration -= dt
            if effect.type == StatusEffectType.POISON:
                self.player.poison_regen_multiplier = min(self.player.poison_regen_multiplier, effect.modifier)
            elif effect.type == StatusEffectType.SHIELD:
                self.player.shield_points += effect.power
            elif effect.type == StatusEffectType.TEMP_DAMAGE_BOOST:
                self.player.temp_damage_boost += effect.power
            if effect.duration > 0:
                alive.append(effect)
        self.player_effects = alive

    def add_enemy_status(self, enemy: Enemy, effect: StatusEffect) -> None:
        enemy.effects.append(effect)

    def add_player_status(self, effect: StatusEffect) -> None:
        self.player_effects.append(effect)

    def absorb_shield_damage(self, incoming: float) -> float:
        if incoming <= 0 or self.player.shield_points <= 0:
            return incoming
        absorbed = min(self.player.shield_points, incoming)
        self.player.shield_points -= absorbed
        incoming -= absorbed
        to_remove = absorbed
        alive = []
        for effect in self.player_effects:
            if effect.type != StatusEffectType.SHIELD or to_remove <= 0:
                alive.append(effect)
                continue
            cut = min(effect.power, to_remove)
            effect.power -= cut
            to_remove -= cut
            if effect.power > 0.01:
                alive.append(effect)
        self.player_effects = alive
        return incoming

    def handle_menu_confirm(self) -> None:
        if self.game_state == GameState.GAME_OVER:
            self.game_state = GameState.MENU
            self.character_select_active = False
            self.selected_menu_action = 0
            self.selected_character_idx = 0
            return
        if not self.character_select_active:
            self.character_select_active = True
            return
        picked = self.characters[self.selected_character_idx]
        if picked.name not in self.save_data.unlocked_characters:
            if self.save_data.total_coins >= picked.cost:
                self.save_data.total_coins -= picked.cost
                self.save_data.unlocked_characters.append(picked.name)
                self.save_system.save(self.save_data)
            else:
                return
        self.start_run_with_character(picked, self.selected_menu_action == 1)

    def start_run_with_character(self, picked: CharacterDef, load: bool) -> None:
        self.reset_run()
        self.unlocked_weapons.add(picked.start_weapon)
        self.player.damage_multiplier *= picked.damage_scale
        self.player.move_speed *= picked.speed_scale
        if load:
            self.score = self.save_data.saved_score
            self.wave = max(1, self.save_data.saved_wave)
            self.world_time = max(0.0, self.save_data.saved_world_time)
            self.run_coins = self.save_data.saved_run_coins
        else:
            self.run_coins = 0
            self.save_data.saved_run_coins = 0
            self.save_data.saved_score = 0
            self.save_data.saved_wave = 1
            self.save_data.saved_world_time = 0.0
        self.save_data.saved_character = picked.name
        self.character_select_active = False
        self.game_state = GameState.PLAYING

    def reset_run(self) -> None:
        self.enemies.clear()
        self.projectiles.clear()
        self.xp_orbs.clear()
        self.damage_numbers.clear()
        self.upgrade_choices.clear()
        self.unlocked_weapons.clear()
        self.unlocked_weapons.add(WeaponType.MAGIC_BOLT)
        self.chain_lightnings.clear()
        self.saw_blades.clear()
        self.particles.clear()
        self.player_effects.clear()
        self.shop_choices.clear()
        self.map_coins.clear()
        self.player.reset()
        self.world_time = 0.0
        self.spawn_timer = 0.4
        self.contact_damage_timer = 0.0
        self.score = 0
        self.pending_level_ups = 0
        self.wave = 1
        self.wave_timer = 0.0
        self.shot_kill_streak = 0
        self.no_damage_time = 0.0
        self.coin_spawn_timer = 5.0
        self.boss_timer = 180.0
        self.extra_weapon_cooldowns.clear()
        self.is_dashing = False
        self.dash_cooldown_timer = 0.0
        self.game_state = GameState.PLAYING
        self.upgrade_state = UpgradeState.NONE

    # --- UI helpers ---
    def _text_w(self, font: pygame.font.Font, text: str) -> int:
        return font.size(text)[0]

    def _blit_centered(self, font: pygame.font.Font, text: str, color: tuple, center_x: int, y: int) -> pygame.Rect:
        surf = font.render(text, True, color)
        rect = surf.get_rect(midtop=(center_x, y))
        self.screen.blit(surf, rect)
        return rect

    def _draw_panel(
        self,
        rect: pygame.Rect,
        *,
        fill: tuple = UI_PANEL,
        alpha: int = 210,
        border: tuple = UI_PANEL_BORDER,
        radius: int = 12,
    ) -> None:
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*fill, alpha), (0, 0, rect.w, rect.h), border_radius=radius)
        pygame.draw.rect(surf, (*border, 220), (0, 0, rect.w, rect.h), width=2, border_radius=radius)
        self.screen.blit(surf, rect.topleft)

    def _draw_bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        ratio: float,
        fill: tuple,
        bg: tuple,
        *,
        radius: int = 6,
    ) -> None:
        ratio = clamp(ratio, 0.0, 1.0)
        pygame.draw.rect(self.screen, bg, (x, y, w, h), border_radius=radius)
        if ratio > 0:
            pygame.draw.rect(self.screen, fill, (x, y, max(2, int(w * ratio)), h), border_radius=radius)
        pygame.draw.rect(self.screen, UI_PANEL_BORDER, (x, y, w, h), width=1, border_radius=radius)

    def _upgrade_card_rect(self, index: int) -> pygame.Rect:
        cx = WIDTH // 2
        top = UPGRADE_START_Y + index * (UPGRADE_CARD_H + UPGRADE_CARD_GAP)
        return pygame.Rect(cx - UPGRADE_CARD_W // 2, top, UPGRADE_CARD_W, UPGRADE_CARD_H)

    def _shop_card_rect(self, index: int) -> pygame.Rect:
        cx = WIDTH // 2
        top = SHOP_START_Y + index * (SHOP_CARD_H + SHOP_CARD_GAP)
        return pygame.Rect(cx - SHOP_CARD_W // 2, top, SHOP_CARD_W, SHOP_CARD_H)

    def _draw_choice_cards(
        self,
        title: str,
        subtitle: str,
        choices: list[str],
        *,
        card_rect_fn,
        accent: tuple = UI_ACCENT,
        card_color: tuple = UI_CARD,
        footer: str = "1–3 или клик · ESC — пропустить",
    ) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 8, 18, 200))
        self.screen.blit(overlay, (0, 0))
        self._blit_centered(self.font_big, title, accent, WIDTH // 2, 100)
        self._blit_centered(self.font_menu, subtitle, UI_TEXT_DIM, WIDTH // 2, 158)
        mouse = pygame.mouse.get_pos()
        for i, choice in enumerate(choices):
            rect = card_rect_fn(i)
            hovered = rect.collidepoint(mouse)
            color = UI_CARD_HOVER if hovered else card_color
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, (*color, 235), (0, 0, rect.w, rect.h), border_radius=14)
            border_c = UI_ACCENT if hovered else UI_PANEL_BORDER
            pygame.draw.rect(surf, (*border_c, 255), (0, 0, rect.w, rect.h), width=2, border_radius=14)
            self.screen.blit(surf, rect.topleft)
            key_surf = self.font_title.render(str(i + 1), True, UI_ACCENT)
            key_rect = key_surf.get_rect(center=(rect.left + 36, rect.centery))
            self.screen.blit(key_surf, key_rect)
            pygame.draw.circle(self.screen, (*UI_ACCENT_DIM, 255), key_rect.center, 22, width=2)
            text = self.font_mid.render(choice, True, UI_TEXT)
            text_rect = text.get_rect(midleft=(rect.left + 72, rect.centery))
            if text_rect.width > rect.w - 88:
                text = self.font_menu.render(choice, True, UI_TEXT)
                text_rect = text.get_rect(midleft=(rect.left + 72, rect.centery))
            self.screen.blit(text, text_rect)
        self._blit_centered(self.font_small, footer, UI_TEXT_DIM, WIDTH // 2, HEIGHT - 52)

    # --- drawing ---
    def blit_sprite(self, sprite: Optional[pygame.Surface], x: float, y: float, hit_flash: bool = False) -> bool:
        if sprite is None:
            return False
        rect = sprite.get_rect(center=(int(x), int(y)))
        if hit_flash:
            temp = sprite.copy()
            temp.set_alpha(153)
            self.screen.blit(temp, rect)
        else:
            self.screen.blit(sprite, rect)
        return True

    def draw(self) -> None:
        self.draw_background()
        self.draw_game()
        self.draw_hud()
        if self.game_state == GameState.MENU:
            self.draw_menu()
        elif self.game_state == GameState.GAME_OVER:
            self.draw_game_over()
        elif self.upgrade_state == UpgradeState.PAUSED_FOR_UPGRADE:
            self.draw_upgrade_overlay()
        elif self.upgrade_state == UpgradeState.PAUSED_FOR_SHOP:
            self.draw_shop_overlay()
        pygame.display.flip()

    def draw_background(self) -> None:
        if self.bg_sprite is not None:
            scaled = pygame.transform.scale(self.bg_sprite, (WIDTH, HEIGHT))
            self.screen.blit(scaled, (0, 0))
            return
        self.screen.fill((15, 15, 22))
        off_x_slow = (self.player.x - WIDTH * 0.5) * 0.08
        off_y_slow = (self.player.y - HEIGHT * 0.5) * 0.08
        off_x_fast = (self.player.x - WIDTH * 0.5) * 0.20
        off_y_fast = (self.player.y - HEIGHT * 0.5) * 0.20
        for i in range(140):
            x = ((i * 97 + self.world_time * 9) % (WIDTH + 200)) - 100 - off_x_slow
            y = ((i * 53 + self.world_time * 7) % (HEIGHT + 200)) - 100 - off_y_slow
            pygame.draw.circle(self.screen, (180, 180, 230), (int(x), int(y)), 1)
        for x in range(-64, WIDTH + 64, 64):
            for y in range(-64, HEIGHT + 64, 64):
                pulse = int((math.sin((x + y + self.world_time * 45) * 0.03) + 1) * 8)
                c = 30 + pulse
                pygame.draw.rect(self.screen, (c, c, 44 + pulse), (int(x - off_x_fast), int(y - off_y_fast), 62, 62))

    def draw_game(self) -> None:
        if self.is_dashing:
            pygame.draw.circle(self.screen, (100, 200, 255), (int(self.player.x), int(self.player.y)), int(self.player.radius * 2), 2)

        for le in self.chain_lightnings:
            pygame.draw.line(self.screen, (200, 220, 255), (int(self.player.x), int(self.player.y)), (int(le.target.x), int(le.target.y)), 4)
            if le.second_target:
                pygame.draw.line(self.screen, (200, 220, 255), (int(le.target.x), int(le.target.y)), (int(le.second_target.x), int(le.second_target.y)), 4)
            if le.third_target:
                pygame.draw.line(self.screen, (200, 220, 255), (int(le.second_target.x), int(le.second_target.y)), (int(le.third_target.x), int(le.third_target.y)), 4)

        for sb in self.saw_blades:
            pygame.draw.circle(self.screen, (210, 210, 210), (int(sb.x), int(sb.y)), int(sb.radius), 2)
            end_x = sb.x + math.cos(sb.angle) * (sb.radius + 5)
            end_y = sb.y + math.sin(sb.angle) * (sb.radius + 5)
            pygame.draw.line(self.screen, (210, 210, 210), (int(sb.x), int(sb.y)), (int(end_x), int(end_y)), 1)

        for orb in self.xp_orbs:
            pygame.draw.circle(self.screen, (80, 180, 255), (int(orb.x), int(orb.y)), 4)
        for coin in self.map_coins:
            pygame.draw.circle(self.screen, (250, 210, 70), (int(coin.x), int(coin.y)), 5)
            pygame.draw.circle(self.screen, (255, 240, 140), (int(coin.x), int(coin.y)), 7, 1)

        for p in self.projectiles:
            pygame.draw.circle(self.screen, (255, 228, 120), (int(p.x), int(p.y)), max(2, int(p.radius)))

        self.draw_particles()

        for e in self.enemies:
            is_tank = e.radius > 18
            sprite = self.enemy_tank_sprite if is_tank else self.enemy_normal_sprite
            if not self.blit_sprite(sprite, e.x, e.y, e.hit_flash_timer > 0):
                color = (155, 52, 52) if is_tank else (190, 75, 75)
                if e.hit_flash_timer > 0:
                    color = (255, 255, 255)
                pygame.draw.circle(self.screen, color, (int(e.x), int(e.y)), int(e.current_radius))
            if e.attack_windup > 0.05:
                r = e.radius + 6 + e.attack_windup * 8
                pygame.draw.circle(self.screen, (255, 80, 80), (int(e.x), int(e.y)), int(r), 2)

        if WeaponType.DAMAGE_AURA in self.unlocked_weapons:
            aura = self.player.aura_radius * self.player.projectile_size_multiplier
            surf = pygame.Surface((int(aura * 2), int(aura * 2)), pygame.SRCALPHA)
            pygame.draw.circle(surf, (150, 90, 255, 65), (int(aura), int(aura)), int(aura))
            self.screen.blit(surf, (int(self.player.x - aura), int(self.player.y - aura)))

        if not self.blit_sprite(self.player_sprite, self.player.x, self.player.y):
            pygame.draw.circle(self.screen, (80, 230, 120), (int(self.player.x), int(self.player.y)), int(self.player.radius))

        for dn in self.damage_numbers:
            alpha = max(0, min(255, int(dn.alpha * 255)))
            txt = self.font.render(str(dn.value), True, (255, 255, 255))
            txt.set_alpha(alpha)
            self.screen.blit(txt, (int(dn.x) - 5, int(dn.y)))

    def _blit_stat_cell(self, x: int, y: int, label: str, value: str, *, value_color: tuple = UI_TEXT, compact: bool = False) -> int:
        """Draw label + value in a fixed-height cell; returns bottom y."""
        self.screen.blit(self.font_label.render(label, True, UI_TEXT_DIM), (x, y))
        value_font = self.font_small if compact else self.font
        self.screen.blit(value_font.render(value, True, value_color), (x, y + 14))
        return y + HUD_STAT_ROW_H

    def draw_hud(self) -> None:
        if self.game_state != GameState.PLAYING:
            return

        hud_rect = pygame.Rect(UI_MARGIN, UI_MARGIN, HUD_W, HUD_H)
        self._draw_panel(hud_rect)

        inner_left = hud_rect.left + HUD_PAD
        inner_right = hud_rect.right - HUD_PAD
        col_w = (inner_right - inner_left) // 2
        col_l = inner_left
        col_r = inner_left + col_w

        stats_top = hud_rect.top + HUD_PAD + HUD_HEADER_H
        self._blit_stat_cell(col_l, stats_top, "УРОВЕНЬ", str(self.player.level), value_color=UI_ACCENT)
        self._blit_stat_cell(col_l, stats_top + HUD_STAT_ROW_H, "ВРЕМЯ", format_time(self.world_time))
        self._blit_stat_cell(
            col_l,
            stats_top + HUD_STAT_ROW_H * 2,
            "СЧЁТ",
            f"{self.score}  ·  {self.run_coins} мон.",
            compact=True,
        )

        self._blit_stat_cell(col_r, stats_top, "ВОЛНА", str(self.wave))
        self._blit_stat_cell(col_r, stats_top + HUD_STAT_ROW_H, "СЕРИЯ", f"x{self.shot_kill_streak}")
        self._blit_stat_cell(
            col_r,
            stats_top + HUD_STAT_ROW_H * 2,
            "РЕКОРД",
            f"{self.save_data.best_multi_kill} уб.",
            compact=True,
        )

        divider_y = stats_top + HUD_STATS_H + 2
        pygame.draw.line(self.screen, UI_PANEL_BORDER, (inner_left, divider_y), (inner_right, divider_y), 1)

        bars_top = stats_top + HUD_STATS_H + HUD_STATS_GAP
        bar_x = inner_left
        bar_w = inner_right - inner_left
        hp_ratio = self.player.hp / max(1.0, self.player.max_hp)
        xp_ratio = self.player.xp / max(1, self.player.xp_to_next)

        hp_label = f"HP {int(self.player.hp)} / {int(self.player.max_hp)}"
        self.screen.blit(self.font_small.render(hp_label, True, UI_TEXT), (bar_x, bars_top))
        self._draw_bar(bar_x, bars_top + 16, bar_w, 12, hp_ratio, UI_HP_FILL, UI_HP_BG)

        xp_top = bars_top + 34
        xp_label = f"XP {self.player.xp} / {self.player.xp_to_next}"
        self.screen.blit(self.font_small.render(xp_label, True, UI_TEXT_DIM), (bar_x, xp_top))
        self._draw_bar(bar_x, xp_top + 16, bar_w, 10, xp_ratio, UI_XP_FILL, UI_XP_BG, radius=5)

        dash_ready = self.dash_cooldown_timer <= 0
        dash_text = "РЫВОК · ПРОБЕЛ" if dash_ready else f"РЫВОК · {math.ceil(self.dash_cooldown_timer):.0f}с"
        dash_color = UI_HP_FILL if dash_ready else UI_TEXT_DIM
        dash_surf = self.font_label.render(dash_text, True, dash_color)
        dash_rect = dash_surf.get_rect(topright=(inner_right, hud_rect.top + HUD_PAD))
        self.screen.blit(dash_surf, dash_rect)

        self.draw_weapon_icons(hud_rect)

    def draw_weapon_icons(self, hud_rect: pygame.Rect) -> None:
        weapons = sorted(self.unlocked_weapons, key=lambda w: w.name)
        if not weapons:
            return
        count = len(weapons)
        bar_w = count * WEAPON_ICON + max(0, count - 1) * WEAPON_GAP + WEAPON_BAR_PAD * 2
        bar_h = WEAPON_ICON + 28
        bar_x = WIDTH - UI_MARGIN - bar_w
        if bar_x < hud_rect.right + UI_MARGIN:
            bar_x = hud_rect.right + UI_MARGIN
        bar_rect = pygame.Rect(bar_x, UI_MARGIN, bar_w, bar_h)
        self._draw_panel(bar_rect, alpha=200)
        self.screen.blit(self.font_label.render("ОРУЖИЕ", True, UI_TEXT_DIM), (bar_rect.left + 12, bar_rect.top + 6))
        x = bar_rect.left + 12
        y = bar_rect.top + 22
        for weapon in weapons:
            slot = pygame.Rect(x, y, WEAPON_ICON, WEAPON_ICON)
            pygame.draw.rect(self.screen, (22, 24, 36), slot, border_radius=8)
            inner = slot.inflate(-6, -6)
            pygame.draw.rect(self.screen, self.get_weapon_color(weapon), inner, border_radius=6)
            short = self.get_weapon_short_name(weapon)
            label = self.font_label.render(short, True, (20, 22, 30))
            label_rect = label.get_rect(center=inner.center)
            self.screen.blit(label, label_rect)
            x += WEAPON_ICON + WEAPON_GAP

    def get_weapon_color(self, weapon: WeaponType) -> tuple:
        colors = {
            WeaponType.MAGIC_BOLT: (100, 200, 255),
            WeaponType.TRIPLE_CAST: (140, 230, 120),
            WeaponType.PULSE_RING: (255, 200, 100),
            WeaponType.PIERCE_LANCE: (255, 120, 120),
            WeaponType.DAMAGE_AURA: (180, 120, 255),
            WeaponType.CHAIN_LIGHTNING: (200, 220, 255),
            WeaponType.SAW_BLADE: (210, 210, 210),
            WeaponType.FROST_NOVA: (120, 220, 255),
            WeaponType.TOXIC_DART: (130, 220, 120),
            WeaponType.FLAME_ORB: (255, 150, 90),
        }
        return colors.get(weapon, (180, 180, 180))

    def get_weapon_short_name(self, weapon: WeaponType) -> str:
        names = {
            WeaponType.MAGIC_BOLT: "МБ",
            WeaponType.TRIPLE_CAST: "ТЗ",
            WeaponType.PULSE_RING: "КИ",
            WeaponType.PIERCE_LANCE: "ПК",
            WeaponType.DAMAGE_AURA: "АУ",
            WeaponType.CHAIN_LIGHTNING: "ЦМ",
            WeaponType.SAW_BLADE: "ПЛ",
            WeaponType.FROST_NOVA: "ЛВ",
            WeaponType.TOXIC_DART: "ЯД",
            WeaponType.FLAME_ORB: "ОШ",
        }
        return names.get(weapon, "??")

    def draw_menu(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 8, 18, 210))
        self.screen.blit(overlay, (0, 0))

        self._blit_centered(self.font_huge, "JAVA SURVIVORS", UI_TEXT, WIDTH // 2, 72)
        tag = self.font_title.render("SURVIVOR ARENA", True, UI_ACCENT)
        self.screen.blit(tag, tag.get_rect(midtop=(WIDTH // 2, 138)))

        if not self.character_select_active:
            menu_w, item_h, gap = 480, 52, 12
            start_y = 260
            for i, label in enumerate(("Новая игра", "Загрузить сохранение")):
                rect = pygame.Rect(WIDTH // 2 - menu_w // 2, start_y + i * (item_h + gap), menu_w, item_h)
                selected = i == self.selected_menu_action
                fill = UI_CARD_HOVER if selected else UI_CARD
                surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                pygame.draw.rect(surf, (*fill, 240), (0, 0, rect.w, rect.h), border_radius=12)
                border_c = UI_ACCENT if selected else UI_PANEL_BORDER
                pygame.draw.rect(surf, (*border_c, 255), (0, 0, rect.w, rect.h), width=2, border_radius=12)
                self.screen.blit(surf, rect.topleft)
                text_color = UI_ACCENT if selected else UI_TEXT
                text = self.font_menu.render(label, True, text_color)
                self.screen.blit(text, text.get_rect(center=rect.center))

            self._blit_centered(self.font_small, "↑ / ↓ — выбор   ·   ENTER — подтвердить", UI_TEXT_DIM, WIDTH // 2, 400)
            coin_line = f"Банк монет: {self.save_data.total_coins}"
            self._blit_centered(self.font_menu, coin_line, UI_ACCENT, WIDTH // 2, 432)
            if self.save_data.high_score > 0:
                self._blit_centered(
                    self.font_small,
                    f"Рекорд счёта: {self.save_data.high_score}",
                    UI_TEXT_DIM,
                    WIDTH // 2,
                    468,
                )
        else:
            self._blit_centered(self.font_mid, "Выбор персонажа", UI_TEXT, WIDTH // 2, 188)
            self._blit_centered(
                self.font_small,
                "1–9, 0 — быстрый выбор   ·   ENTER — начать",
                UI_TEXT_DIM,
                WIDTH // 2,
                224,
            )
            list_w, row_h = 720, 40
            list_top = 252
            for i, c in enumerate(self.characters):
                rect = pygame.Rect(WIDTH // 2 - list_w // 2, list_top + i * row_h, list_w, row_h - 6)
                selected = i == self.selected_character_idx
                unlocked = c.name in self.save_data.unlocked_characters
                if selected:
                    pygame.draw.rect(self.screen, UI_CARD_HOVER, rect, border_radius=8)
                    pygame.draw.rect(self.screen, UI_ACCENT, rect, width=2, border_radius=8)
                elif i % 2 == 0:
                    pygame.draw.rect(self.screen, (*UI_CARD, 120), rect, border_radius=8)

                name_color = UI_ACCENT if selected else UI_TEXT
                self.screen.blit(self.font_menu.render(f"{i + 1}.", True, UI_TEXT_DIM), (rect.left + 12, rect.centery - 12))
                self.screen.blit(self.font_menu.render(c.name, True, name_color), (rect.left + 44, rect.centery - 12))
                weapon_short = self.get_weapon_short_name(c.start_weapon)
                self.screen.blit(
                    self.font_small.render(weapon_short, True, self.get_weapon_color(c.start_weapon)),
                    (rect.left + 180, rect.centery - 10),
                )
                if unlocked:
                    status, status_color = "Открыт", UI_HP_FILL
                elif self.save_data.total_coins >= c.cost:
                    status, status_color = f"Купить · {c.cost}", UI_ACCENT
                else:
                    status, status_color = f"Закрыт · {c.cost}", (200, 90, 90)
                status_surf = self.font_small.render(status, True, status_color)
                self.screen.blit(status_surf, status_surf.get_rect(right=rect.right - 14, centery=rect.centery))

    def draw_game_over(self) -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 8, 18, 210))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 520, 340
        panel = pygame.Rect(WIDTH // 2 - panel_w // 2, HEIGHT // 2 - panel_h // 2 - 20, panel_w, panel_h)
        self._draw_panel(panel, fill=(28, 18, 22), border=(120, 50, 55))

        self._blit_centered(self.font_huge, "ВЫ ПОГИБЛИ", (255, 110, 110), WIDTH // 2, panel.top + 28)
        self._blit_centered(
            self.font_mid,
            f"Время: {format_time(self.world_time)}",
            UI_TEXT,
            WIDTH // 2,
            panel.top + 120,
        )
        self._blit_centered(self.font_mid, f"Счёт: {self.score}", UI_ACCENT, WIDTH // 2, panel.top + 168)
        self._blit_centered(
            self.font_small,
            f"Волна {self.wave}  ·  Монеты забега {self.run_coins}",
            UI_TEXT_DIM,
            WIDTH // 2,
            panel.top + 210,
        )
        if self.score >= self.save_data.high_score and self.score > 0:
            self._blit_centered(self.font_label, "НОВЫЙ РЕКОРД!", UI_ACCENT, WIDTH // 2, panel.top + 244)

        hint_rect = pygame.Rect(panel.left + 40, panel.bottom - 58, panel.w - 80, 40)
        pygame.draw.rect(self.screen, UI_CARD, hint_rect, border_radius=10)
        hint_surf = self.font_menu.render("ENTER — в меню", True, UI_TEXT)
        self.screen.blit(hint_surf, hint_surf.get_rect(center=hint_rect.center))

    def draw_upgrade_overlay(self) -> None:
        self._draw_choice_cards(
            "Улучшение",
            f"Уровень {self.player.level}  ·  выберите одну карту",
            self.upgrade_choices,
            card_rect_fn=self._upgrade_card_rect,
            accent=(180, 200, 255),
            footer="1–3 или клик по карте",
        )

    def draw_shop_overlay(self) -> None:
        self._draw_choice_cards(
            "Магазин",
            f"Очки: {self.score}",
            self.shop_choices,
            card_rect_fn=self._shop_card_rect,
            accent=UI_ACCENT,
            card_color=UI_SHOP_CARD,
            footer="1–3 или клик · ESC — пропустить магазин",
        )


if __name__ == "__main__":
    Game().run()

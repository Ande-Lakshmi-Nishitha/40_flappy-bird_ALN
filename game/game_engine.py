import array
import math

import pygame
from .bird import Bird
from .pipe import Pipe

# Game Engine

WHITE = (255, 255, 255)
GREEN = (0, 150, 0)
YELLOW = (255, 220, 80)

# Game states
MENU = "menu"
PLAYING = "playing"
GAME_OVER = "game_over"

# Difficulty presets. "spacing" is the horizontal distance between pipes in
# pixels, so the spawn interval (in frames) is derived from speed and the
# layout stays fair at every difficulty.
DIFFICULTIES = {
    "Easy":   {"speed": 3, "gap": 190, "spacing": 320},
    "Medium": {"speed": 4, "gap": 150, "spacing": 360},
    "Hard":   {"speed": 5, "gap": 125, "spacing": 330},
}

DIFFICULTY_KEYS = {
    pygame.K_1: "Easy",
    pygame.K_2: "Medium",
    pygame.K_3: "Hard",
}


def _make_tone(freq_start, freq_end, duration, volume=0.3):
    """Generate a short sine sweep as a pygame Sound (no asset files needed)."""
    init = pygame.mixer.get_init()
    if not init:
        return None
    rate, fmt, channels = init
    if fmt != -16:  # only signed 16-bit is handled here
        return None

    n = int(rate * duration)
    samples = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = freq_start + (freq_end - freq_start) * t
        phase += 2 * math.pi * freq / rate
        value = int(32767 * volume * (1 - t) * math.sin(phase))  # fade out
        for _ in range(channels):
            samples.append(value)
    return pygame.mixer.Sound(buffer=samples.tobytes())


class GameEngine:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.font = pygame.font.SysFont("Arial", 30)
        self.title_font = pygame.font.SysFont("Arial", 56, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 24)

        self.overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, 150))

        self.sounds = self._load_sounds()

        self.reset("Medium")
        self.state = MENU  # the game opens on the start screen

    # ------------------------------------------------------------------ setup

    def _load_sounds(self):
        # Sound is optional: if there's no audio device the game still runs.
        try:
            return {
                "flap": _make_tone(400, 700, 0.12),
                "score": _make_tone(800, 1100, 0.10),
                "die": _make_tone(400, 90, 0.40, volume=0.4),
            }
        except pygame.error:
            return {}

    def _play(self, name):
        sound = self.sounds.get(name)
        if sound:
            sound.play()

    def reset(self, difficulty="Medium"):
        """Start a fresh round at the given difficulty."""
        settings = DIFFICULTIES[difficulty]
        self.difficulty = difficulty
        self.pipe_speed = settings["speed"]
        self.pipe_gap = settings["gap"]
        self.pipe_interval = max(1, round(settings["spacing"] / self.pipe_speed))

        self.bird = Bird(self.width // 4, self.height // 2)
        self._spawn_timer = 0
        self.pipes = [self._new_pipe(self.width + 100)]
        self.score = 0
        self.state = PLAYING

    def show_menu(self):
        """Return to the start screen, keeping the last chosen difficulty."""
        self.reset(self.difficulty)
        self.state = MENU

    def _new_pipe(self, x):
        return Pipe(x, self.height, gap=self.pipe_gap, speed=self.pipe_speed)

    @property
    def game_over(self):
        return self.state == GAME_OVER

    # ------------------------------------------------------- centralized events

    def flap(self):
        self.bird.flap()
        self._play("flap")

    def score_point(self):
        self.score += 1
        self._play("score")

    def die(self):
        if self.state == GAME_OVER:
            return
        self.state = GAME_OVER
        self._play("die")

    # ------------------------------------------------------------------- input

    def handle_event(self, event):
        if self.state == MENU:
            if event.type == pygame.KEYDOWN:
                if event.key in DIFFICULTY_KEYS:
                    self.reset(DIFFICULTY_KEYS[event.key])
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self.reset(self.difficulty)  # start with the default/last difficulty
                elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.event.post(pygame.event.Event(pygame.QUIT))

        elif self.state == PLAYING:
            # Flap is edge-triggered (KEYDOWN / MOUSEBUTTONDOWN), not held.
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                self.flap()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.flap()

        elif self.state == GAME_OVER:
            if event.type == pygame.KEYDOWN:
                if event.key in DIFFICULTY_KEYS:
                    self.reset(DIFFICULTY_KEYS[event.key])
                elif event.key == pygame.K_m:
                    self.show_menu()
                elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.event.post(pygame.event.Event(pygame.QUIT))

    def handle_input(self):
        # Reserved for continuously-held-key input; nothing to poll here.
        pass

    # ------------------------------------------------------------------ update

    def update(self):
        if self.state != PLAYING:
            return

        self.bird.update()

        if self.bird.y - self.bird.radius <= 0 or self.bird.y + self.bird.radius >= self.height:
            self.die()
            return

        self._spawn_timer += 1
        if self._spawn_timer >= self.pipe_interval:
            self._spawn_timer = 0
            self.pipes.append(self._new_pipe(self.width))

        for pipe in self.pipes:
            pipe.move()

            if (self.bird.collides_with_rect(pipe.top_rect())
                    or self.bird.collides_with_rect(pipe.bottom_rect())):
                self.die()
                return

            if not pipe.scored and pipe.x + pipe.width < self.bird.x:
                pipe.scored = True
                self.score_point()

        self.pipes = [p for p in self.pipes if not p.off_screen()]

    # ------------------------------------------------------------------ render

    def _draw_centered(self, screen, font, text, y, color=WHITE):
        surface = font.render(text, True, color)
        screen.blit(surface, surface.get_rect(center=(self.width // 2, y)))

    def render(self, screen):
        for pipe in self.pipes:
            pygame.draw.rect(screen, GREEN, pipe.top_rect())
            pygame.draw.rect(screen, GREEN, pipe.bottom_rect())

        pygame.draw.circle(screen, WHITE, (int(self.bird.x), int(self.bird.y)), self.bird.radius)

        if self.state == MENU:
            self._render_menu(screen)
            return

        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        screen.blit(score_text, (10, 10))

        if self.state == GAME_OVER:
            self._render_game_over(screen)

    def _render_menu(self, screen):
        screen.blit(self.overlay, (0, 0))
        cy = self.height // 2

        self._draw_centered(screen, self.title_font, "Flappy Bird", cy - 160, YELLOW)
        self._draw_centered(screen, self.small_font, "Space / Click to flap", cy - 100)
        self._draw_centered(screen, self.small_font, "Avoid the pipes, the ground and the ceiling", cy - 70)

        self._draw_centered(screen, self.font, "Choose difficulty to start:", cy - 10)
        self._draw_centered(screen, self.small_font, "1 - Easy", cy + 35)
        self._draw_centered(screen, self.small_font, "2 - Medium", cy + 67)
        self._draw_centered(screen, self.small_font, "3 - Hard", cy + 99)
        self._draw_centered(screen, self.small_font,
                            f"Space / Enter - start ({self.difficulty})", cy + 150)
        self._draw_centered(screen, self.small_font, "Esc / Q - Quit", cy + 190)

    def _render_game_over(self, screen):
        screen.blit(self.overlay, (0, 0))
        cy = self.height // 2

        self._draw_centered(screen, self.title_font, "Game Over", cy - 120, YELLOW)
        self._draw_centered(screen, self.font, f"Final score: {self.score}", cy - 55)
        self._draw_centered(screen, self.small_font, f"Last difficulty: {self.difficulty}", cy - 20)

        self._draw_centered(screen, self.font, "Play again:", cy + 40)
        self._draw_centered(screen, self.small_font, "1 - Easy", cy + 80)
        self._draw_centered(screen, self.small_font, "2 - Medium", cy + 112)
        self._draw_centered(screen, self.small_font, "3 - Hard", cy + 144)
        self._draw_centered(screen, self.small_font, "M - Main menu", cy + 185)
        self._draw_centered(screen, self.small_font, "Esc / Q - Quit", cy + 217)
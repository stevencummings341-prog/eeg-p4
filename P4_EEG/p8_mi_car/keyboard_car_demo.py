import random
import sys

try:
    import pygame
except ImportError as exc:
    raise SystemExit("This program requires pygame. Install it with: pip install pygame") from exc


WIDTH = 480
HEIGHT = 720
FPS = 60
ROAD_WIDTH = 320
ROAD_LEFT = (WIDTH - ROAD_WIDTH) // 2
ROAD_RIGHT = ROAD_LEFT + ROAD_WIDTH
LANE_COUNT = 3
LANE_WIDTH = ROAD_WIDTH // LANE_COUNT
CAR_WIDTH = 48
CAR_HEIGHT = 84
CAR_Y = HEIGHT - 120
SCROLL_SPEED = 4
OBSTACLE_WIDTH = 40
OBSTACLE_HEIGHT = 72
COIN_SIZE = 28
HIT_COOLDOWN_FRAMES = 18

GRASS = (28, 122, 61)
ROAD = (55, 55, 55)
ROAD_EDGE = (230, 208, 74)
LANE = (235, 235, 235)
CAR_COLOR = (60, 150, 255)
CAR_WINDOW = (190, 235, 255)
WHEEL = (20, 20, 20)
OBSTACLE = (214, 76, 76)
OBSTACLE_ACCENT = (255, 181, 181)
COIN = (245, 211, 58)
COIN_INNER = (255, 237, 143)
TEXT = (255, 255, 255)
PANEL = (20, 20, 20)
PANEL_BORDER = (180, 180, 180)


def load_font(size):
    for name in ("Microsoft YaHei", "SimHei", "SimSun", "Arial"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def lane_center_x(lane_index, width):
    lane_left = ROAD_LEFT + lane_index * LANE_WIDTH
    return lane_left + (LANE_WIDTH - width) // 2


class CarGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("2D Keyboard Car Demo")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = load_font(26)
        self.small_font = load_font(20)
        self.reset()

    def reset(self):
        self.car_lane = 1
        self.car_rect = pygame.Rect(0, 0, CAR_WIDTH, CAR_HEIGHT)
        self.car_rect.x = lane_center_x(self.car_lane, CAR_WIDTH)
        self.car_rect.y = CAR_Y
        self.road_offset = 0
        self.coin_count = 0
        self.hit_count = 0
        self.hit_cooldown = 0
        self.obstacles = []
        self.coins = []
        self.obstacle_timer = random.randint(FPS * 3, FPS * 4)
        self.coin_timer = random.randint(30, 55)

    def spawn_obstacle(self):
        lane_index = random.randint(0, LANE_COUNT - 1)
        x = lane_center_x(lane_index, OBSTACLE_WIDTH)
        rect = pygame.Rect(x, -OBSTACLE_HEIGHT, OBSTACLE_WIDTH, OBSTACLE_HEIGHT)
        self.obstacles.append(rect)

    def spawn_coin(self):
        lane_index = random.randint(0, LANE_COUNT - 1)
        x = lane_center_x(lane_index, COIN_SIZE)
        rect = pygame.Rect(x, -COIN_SIZE, COIN_SIZE, COIN_SIZE)
        self.coins.append(rect)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.car_lane = max(0, self.car_lane - 1)
                    self.car_rect.x = lane_center_x(self.car_lane, CAR_WIDTH)
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.car_lane = min(LANE_COUNT - 1, self.car_lane + 1)
                    self.car_rect.x = lane_center_x(self.car_lane, CAR_WIDTH)
        return True

    def update_car(self):
        self.car_rect.x = lane_center_x(self.car_lane, CAR_WIDTH)

    def update_objects(self):
        self.road_offset = (self.road_offset + SCROLL_SPEED) % 40

        self.obstacle_timer -= 1
        if self.obstacle_timer <= 0:
            self.spawn_obstacle()
            self.obstacle_timer = random.randint(FPS * 3, FPS * 4)

        self.coin_timer -= 1
        if self.coin_timer <= 0:
            self.spawn_coin()
            self.coin_timer = random.randint(24, 48)

        for obstacle in self.obstacles[:]:
            obstacle.y += SCROLL_SPEED
            if obstacle.top > HEIGHT:
                self.obstacles.remove(obstacle)

        for coin in self.coins[:]:
            coin.y += SCROLL_SPEED
            if coin.top > HEIGHT:
                self.coins.remove(coin)

        hit_objects = [obstacle for obstacle in self.obstacles if self.car_rect.colliderect(obstacle)]
        if hit_objects:
            if self.hit_cooldown == 0:
                self.hit_count += 1
                self.hit_cooldown = HIT_COOLDOWN_FRAMES
            for obstacle in hit_objects:
                if obstacle in self.obstacles:
                    self.obstacles.remove(obstacle)

        collected = [coin for coin in self.coins if self.car_rect.colliderect(coin)]
        if collected:
            self.coin_count += len(collected)
            for coin in collected:
                if coin in self.coins:
                    self.coins.remove(coin)

        if self.hit_cooldown > 0:
            self.hit_cooldown -= 1

    def draw_background(self):
        self.screen.fill(GRASS)
        pygame.draw.rect(self.screen, ROAD, (ROAD_LEFT, 0, ROAD_WIDTH, HEIGHT))
        pygame.draw.line(self.screen, ROAD_EDGE, (ROAD_LEFT, 0), (ROAD_LEFT, HEIGHT), 4)
        pygame.draw.line(self.screen, ROAD_EDGE, (ROAD_RIGHT, 0), (ROAD_RIGHT, HEIGHT), 4)

        lane_positions = [ROAD_LEFT + LANE_WIDTH * index for index in range(1, LANE_COUNT)]
        for lane_x in lane_positions:
            for y in range(-40, HEIGHT + 40, 40):
                top = y + self.road_offset
                pygame.draw.rect(self.screen, LANE, (lane_x - 4, top, 8, 24), border_radius=3)

    def draw_obstacles(self):
        for obstacle in self.obstacles:
            pygame.draw.rect(self.screen, OBSTACLE, obstacle, border_radius=8)
            highlight = obstacle.inflate(-18, -20)
            pygame.draw.rect(self.screen, OBSTACLE_ACCENT, highlight, border_radius=6)

    def draw_coins(self):
        for coin in self.coins:
            center = coin.center
            radius = coin.width // 2
            pygame.draw.circle(self.screen, COIN, center, radius)
            pygame.draw.circle(self.screen, COIN_INNER, center, radius - 6)
            pygame.draw.circle(self.screen, COIN, center, radius, 3)

    def draw_car(self):
        if self.hit_cooldown > 0 and self.hit_cooldown % 4 < 2:
            body_color = (255, 110, 110)
        else:
            body_color = CAR_COLOR

        body = self.car_rect
        cabin = pygame.Rect(body.x + 8, body.y + 12, body.width - 16, body.height - 28)
        windshield = pygame.Rect(body.x + 12, body.y + 18, body.width - 24, body.height - 42)

        pygame.draw.rect(self.screen, body_color, body, border_radius=12)
        pygame.draw.rect(self.screen, CAR_WINDOW, cabin, border_radius=10)
        pygame.draw.rect(self.screen, (245, 245, 245), windshield, border_radius=8)

        wheel_width = 8
        wheel_height = 18
        wheel_positions = [
            (body.left - 4, body.y + 10),
            (body.left - 4, body.bottom - 28),
            (body.right - wheel_width + 4, body.y + 10),
            (body.right - wheel_width + 4, body.bottom - 28),
        ]
        for x, y in wheel_positions:
            pygame.draw.rect(self.screen, WHEEL, (x, y, wheel_width, wheel_height), border_radius=4)

    def draw_overlay(self):
        panel_rect = pygame.Rect(WIDTH - 170, 18, 150, 90)
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=10)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, width=2, border_radius=10)

        coin_text = self.font.render(f"金币: {self.coin_count}", True, TEXT)
        hit_text = self.font.render(f"碰撞: {self.hit_count}", True, TEXT)
        help_text = self.small_font.render("← → 控制  R 重开  ESC 退出", True, TEXT)

        self.screen.blit(coin_text, (panel_rect.right - coin_text.get_width() - 12, panel_rect.y + 14))
        self.screen.blit(hit_text, (panel_rect.right - hit_text.get_width() - 12, panel_rect.y + 48))
        self.screen.blit(help_text, (20, 20))

    def draw(self):
        self.draw_background()
        self.draw_obstacles()
        self.draw_coins()
        self.draw_car()
        self.draw_overlay()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            running = self.handle_events()
            self.update_car()
            self.update_objects()
            self.draw()
        pygame.quit()


def main():
    game = CarGame()
    game.run()


if __name__ == "__main__":
    main()

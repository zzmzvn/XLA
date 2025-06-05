import pygame
import random
import sys
import threading
import cv2
import mediapipe as mp
import numpy as np
import queue
import math
import time
import os

pygame.init()
HIGH_SCORE_FILE = "highscore.txt"
if os.path.exists(HIGH_SCORE_FILE):
    with open(HIGH_SCORE_FILE, "r") as f:
        try:
            high_score = int(f.read())
        except:
            high_score = 0
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Duck Hunt - Hand Control")
clock = pygame.time.Clock()

background = pygame.transform.scale(pygame.image.load("bg2.png").convert(), (WIDTH, HEIGHT))
duck_imgs_right = [
    pygame.transform.scale(pygame.image.load("d1.png").convert_alpha(), (50, 50)),
    pygame.transform.scale(pygame.image.load("d2.png").convert_alpha(), (50, 50))
]
duck_imgs_left = [
    pygame.transform.scale(pygame.image.load("d3.png").convert_alpha(), (50, 50)),
    pygame.transform.scale(pygame.image.load("d4.png").convert_alpha(), (50, 50))
]
crosshair_img = pygame.transform.scale(pygame.image.load("ot.png").convert_alpha(), (40, 40))

hit_effect_img = pygame.transform.scale(pygame.image.load("hit.png").convert_alpha(), (60, 60))
hit_effects = []

hit_sound = pygame.mixer.Sound("hit_sound.wav")
miss_sound = pygame.mixer.Sound("miss_sound.wav")

WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)

ducks = []
score = 0
high_score = 0
speed_multiplier = 1.0
MAX_AMMO = 3
ammo = MAX_AMMO

hand_x, hand_y = WIDTH // 2, HEIGHT // 2
smoothed_hand_x, smoothed_hand_y = hand_x, hand_y
SMOOTHING_FACTOR = 0.3

webcam_frame = None
hand_landmarks_queue = queue.Queue()

font = pygame.font.SysFont(None, 36)
large_font = pygame.font.SysFont(None, 48)
hit_status = ""
hit_timer = 0
last_shot_time = 0
shot_cooldown = 200
game_running = True
is_reloading = False
last_menu_action_time = 0
menu_action_cooldown = 500

MENU_MAIN = 0
MENU_TIME_MODE = 1
GAME_CLASSIC = 2
GAME_TIME_MODE = 3
GAME_OVER = 4
current_state = MENU_MAIN

time_mode_level = 0
time_mode_settings = [
    {'time_limit': 30, 'target_ducks': 3},
    {'time_limit': 45, 'target_ducks': 5},
    {'time_limit': 60, 'target_ducks': 10},
    {'time_limit': 90, 'target_ducks': 15},
    {'time_limit': 120, 'target_ducks': 20}
]
start_time = 0
time_remaining = 0
game_result = ""
is_winner = False
unlocked_level = 0

def spawn_duck():
    global speed_multiplier
    direction = random.choice(['left', 'right'])
    if direction == 'left':
        x = -50
        y = random.randint(100, HEIGHT - 100)
        speed_x = random.uniform(3, 5) * speed_multiplier
    else:
        x = WIDTH + 50
        y = random.randint(100, HEIGHT - 100)
        speed_x = random.uniform(-5, -3) * speed_multiplier
    speed_y = random.uniform(-1, 1) * speed_multiplier
    ducks.append({
        'pos': [x, y],
        'speed_x': speed_x,
        'speed_y': speed_y,
        'img_index': 0,
        'frame_timer': 0
    })

def reset_game():
    global ducks, score, hit_status, hit_timer, ammo, speed_multiplier, hit_effects, start_time, time_remaining
    ducks.clear()
    score = 0
    hit_status = ""
    hit_timer = 0
    ammo = MAX_AMMO
    speed_multiplier = 1.0
    hit_effects.clear()
    if current_state == GAME_TIME_MODE:
        time_remaining = time_mode_settings[time_mode_level]['time_limit']
        time_mode_settings[time_mode_level]['target_ducks'] = {0: 3, 1: 5, 2: 10}[time_mode_level]
        start_time = time.time()
    # Spawn 2 ducks initially
    spawn_duck()
    spawn_duck()
    if current_state == GAME_CLASSIC:
        # Keep 2 ducks on screen in Classic mode
        while len(ducks) < 2:
            spawn_duck()

def detect_shoot_gesture(hand_landmarks):
    t = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.THUMB_TIP]
    i = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
    dist = math.hypot(t.x - i.x, t.y - i.y)
    return dist < 0.07

def detect_reload_gesture(hand_landmarks):
    t = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.THUMB_TIP]
    i = hand_landmarks.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
    dist = math.hypot(t.x - i.x, t.y - i.y)
    return dist > 0.15

def hand_tracking():
    global hand_x, hand_y, webcam_frame, game_running
    cap = cv2.VideoCapture(0)
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=1)
    mp_drawing = mp.solutions.drawing_utils
    try:
        while game_running:
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            if result.multi_hand_landmarks:
                for lm in result.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)
                    idx = lm.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
                    hand_x = int(idx.x * WIDTH)
                    hand_y = int(idx.y * HEIGHT)
                    try:
                        hand_landmarks_queue.put_nowait(lm)
                    except queue.Full:
                        pass
            small = cv2.resize(frame, (160, 120))
            webcam_frame = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()

def draw_button(text, x, y, w, h, hover=False):
    color = BLUE if hover else BLACK
    pygame.draw.rect(screen, WHITE, (x, y, w, h))
    pygame.draw.rect(screen, color, (x, y, w, h), 2)
    text_surf = font.render(text, True, color)
    text_rect = text_surf.get_rect(center=(x + w // 2, y + h // 2))
    screen.blit(text_surf, text_rect)
    return pygame.Rect(x, y, w, h)

def draw_menu():
    global current_state, time_mode_level, last_menu_action_time, is_winner, unlocked_level
    screen.blit(background, (0, 0))
    now = pygame.time.get_ticks()
    if now - last_menu_action_time < menu_action_cooldown:
        return True

    mouse_x, mouse_y = pygame.mouse.get_pos()

    if current_state == MENU_MAIN:
        title = large_font.render("Duck Hunt", True, BLACK)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
        buttons = [
            ("Classic Mode", WIDTH // 2 - 100, 250, 200, 50),
            ("Time Mode", WIDTH // 2 - 100, 320, 200, 50),
            ("Exit", WIDTH // 2 - 100, 390, 200, 50)
        ]
        for text, x, y, w, h in buttons:
            rect = draw_button(text, x, y, w, h, pygame.Rect(x, y, w, h).collidepoint(mouse_x, mouse_y))
            if rect.collidepoint(mouse_x, mouse_y) and pygame.mouse.get_pressed()[0]:
                last_menu_action_time = now
                if text == "Classic Mode":
                    current_state = GAME_CLASSIC
                    reset_game()
                elif text == "Time Mode":
                    current_state = MENU_TIME_MODE
                elif text == "Exit":
                    return False
    elif current_state == MENU_TIME_MODE:
        title = large_font.render("Time Mode", True, BLACK)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
        buttons = []
        start_y = 180  # <-- thay vì 250, bắt đầu cao hơn
        spacing = 60   # <-- giảm khoảng cách giữa các nút
        for i in range(len(time_mode_settings)):
            y = start_y + i * spacing
            buttons.append((f"Level {i + 1}", WIDTH // 2 - 150, y, 300, 50))
        buttons.append(("Back", WIDTH // 2 - 100, start_y + len(time_mode_settings) * spacing + 20, 200, 50))


        for i, (text, x, y, w, h) in enumerate(buttons):
            raw_text = text  # giữ lại tên gốc như "Level 1"
            is_unlocked = True
            if raw_text.startswith("Level"):
                level_num = i  # Level 1: i=0, Level 2: i=1,...
                is_unlocked = level_num <= unlocked_level
                text_display = raw_text + (" (Locked)" if not is_unlocked else "")
            else:
                text_display = raw_text

            rect = draw_button(text_display, x, y, w, h, pygame.Rect(x, y, w, h).collidepoint(mouse_x, mouse_y))

            if rect.collidepoint(mouse_x, mouse_y) and pygame.mouse.get_pressed()[0]:
                last_menu_action_time = now
                if raw_text.startswith("Level") and is_unlocked:
                    time_mode_level = level_num
                    current_state = GAME_TIME_MODE
                    reset_game()
                elif raw_text == "Back":
                    current_state = MENU_MAIN

    elif current_state == GAME_OVER:
        screen.blit(background, (0, 0))
        title = large_font.render("Winner" if is_winner else "Game Over", True, BLACK)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
        result_text = large_font.render(game_result, True, RED if "Failed" in game_result else BLACK)
        screen.blit(result_text, (WIDTH // 2 - result_text.get_width() // 2, 200))
        if current_state == GAME_CLASSIC:
            score_text = font.render(f"Score: {score}", True, BLACK)
            screen.blit(score_text, (WIDTH // 2 - score_text.get_width() // 2, 300))
        back_button = draw_button("Back to Menu", WIDTH // 2 - 100, 350, 200, 50,
                                 pygame.Rect(WIDTH // 2 - 100, 350, 200, 50).collidepoint(mouse_x, mouse_y))
        next_level_button = draw_button("Next Level" if is_winner else "Play Again", WIDTH // 2 - 100, 420, 200, 50,
                                       pygame.Rect(WIDTH // 2 - 100, 420, 200, 50).collidepoint(mouse_x, mouse_y))
        if back_button.collidepoint(mouse_x, mouse_y) and pygame.mouse.get_pressed()[0]:
            last_menu_action_time = now
            current_state = MENU_MAIN
        elif next_level_button.collidepoint(mouse_x, mouse_y) and pygame.mouse.get_pressed()[0]:
            last_menu_action_time = now
            if is_winner and time_mode_level < len(time_mode_settings) - 1:
                time_mode_level += 1
                if time_mode_level > unlocked_level:
                    unlocked_level = time_mode_level
                current_state = GAME_TIME_MODE
                reset_game()
            else:
                if current_state == GAME_OVER and time_mode_level >= 0:
                    current_state = GAME_TIME_MODE
                    reset_game()
                else:
                    current_state = GAME_CLASSIC
                    reset_game()
    return True

threading.Thread(target=hand_tracking, daemon=True).start()

while game_running:
    clock.tick(60)
    screen.blit(background, (0, 0))
    now = pygame.time.get_ticks()

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            game_running = False
        if e.type == pygame.KEYDOWN and e.key == pygame.K_r and current_state in [GAME_CLASSIC, GAME_TIME_MODE]:
            reset_game()

    shoot = False
    reload_gesture = False
    if current_state in [MENU_MAIN, MENU_TIME_MODE, GAME_OVER]:
        mouse_x, mouse_y = pygame.mouse.get_pos()
        smoothed_hand_x, smoothed_hand_y = mouse_x, mouse_y
    else:
        if webcam_frame is not None:
            lm = None
            try:
                while not hand_landmarks_queue.empty():
                    lm = hand_landmarks_queue.get_nowait()
            except queue.Empty:
                pass
            if lm:
                idx = lm.landmark[mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP]
                hand_x = int(idx.x * WIDTH)
                hand_y = int(idx.y * HEIGHT)
                shoot = detect_shoot_gesture(lm)
                reload_gesture = detect_reload_gesture(lm)
        smoothed_hand_x += (hand_x - smoothed_hand_x) * SMOOTHING_FACTOR
        smoothed_hand_y += (hand_y - smoothed_hand_y) * SMOOTHING_FACTOR

    if current_state in [MENU_MAIN, MENU_TIME_MODE, GAME_OVER]:
        game_running = draw_menu()
        screen.blit(crosshair_img, (int(smoothed_hand_x) - 20, int(smoothed_hand_y) - 20))
        pygame.display.update()
        continue

    if reload_gesture and not is_reloading:
        ammo = MAX_AMMO
        is_reloading = True
    if not reload_gesture:
        is_reloading = False

    if shoot and now - last_shot_time > shot_cooldown and ammo > 0:
        last_shot_time = now
        ammo -= 1
        hit = False
        for d in ducks[:]:
            dx, dy = d['pos']
            imgs = duck_imgs_right if d['speed_x'] >= 0 else duck_imgs_left
            rect = imgs[d['img_index']].get_rect(center=(dx, dy))
            if rect.collidepoint(smoothed_hand_x, smoothed_hand_y):
                ducks.remove(d)
                score += 1
                if score > high_score:
                    high_score = score
                    with open(HIGH_SCORE_FILE, "w") as f:
                        f.write(str(high_score))
                if current_state == GAME_CLASSIC and score % 10 == 0:
                    speed_multiplier *= 1.05
                if current_state == GAME_TIME_MODE:
                    time_mode_settings[time_mode_level]['target_ducks'] -= 1
                spawn_duck()
                hit_status = "TRÚNG!"
                hit_timer = 30
                hit = True
                hit_sound.play()
                hit_effects.append({'pos': (dx, dy), 'timer': 12})
                break
        if not hit:
            miss_sound.play()

    for d in ducks[:]:
        d['pos'][0] += d['speed_x']
        d['pos'][1] += d['speed_y']
        if d['pos'][0] < -60 or d['pos'][0] > WIDTH + 60:
            ducks.remove(d)
            spawn_duck()
            continue
        d['frame_timer'] += 1
        if d['frame_timer'] >= 10:
            d['img_index'] = (d['img_index'] + 1) % 2
            d['frame_timer'] = 0

    if current_state == GAME_TIME_MODE:
        time_remaining = time_mode_settings[time_mode_level]['time_limit'] - (time.time() - start_time)
        if time_remaining <= 0 or time_mode_settings[time_mode_level]['target_ducks'] <= 0:
            is_winner = time_mode_settings[time_mode_level]['target_ducks'] <= 0
            if is_winner:
                game_result = f"Level {time_mode_level + 1} Success!"
            else:
                game_result = f"Level {time_mode_level + 1} Failed!"
            current_state = GAME_OVER
            continue

    for duck in ducks:
        imgs = duck_imgs_right if duck['speed_x'] >= 0 else duck_imgs_left
        screen.blit(imgs[duck['img_index']], (duck['pos'][0] - 25, duck['pos'][1] - 25))

    for eff in hit_effects[:]:
        eff['timer'] -= 1
        if eff['timer'] <= 0:
            hit_effects.remove(eff)
        else:
            screen.blit(hit_effect_img, (eff['pos'][0] - 30, eff['pos'][1] - 30))

    screen.blit(crosshair_img, (int(smoothed_hand_x) - 20, int(smoothed_hand_y) - 20))
    if current_state == GAME_CLASSIC:
        screen.blit(font.render(f"Score: {score}", True, BLACK), (10, 10))
        screen.blit(font.render(f"High Score: {high_score}", True, BLACK), (10, 90))

    screen.blit(font.render(f"Shot: {ammo}/{MAX_AMMO}", True, BLACK), (10, 50))
    if current_state == GAME_TIME_MODE:
        screen.blit(font.render(f"Time: {int(time_remaining)}s", True, BLACK), (10, 90))
        screen.blit(font.render(f"Target: {time_mode_settings[time_mode_level]['target_ducks']}", True, BLACK), (10, 130))

    if hit_timer > 0:
        screen.blit(font.render(hit_status, True, RED), (WIDTH // 2 - 40, 80))
        hit_timer -= 1

    if webcam_frame is not None:
        surf = pygame.surfarray.make_surface(webcam_frame.swapaxes(0, 1))
        screen.blit(surf, (WIDTH - 170, HEIGHT - 130))

    pygame.display.update()

pygame.quit()
sys.exit()
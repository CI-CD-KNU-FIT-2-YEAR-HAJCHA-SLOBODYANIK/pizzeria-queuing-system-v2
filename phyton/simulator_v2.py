"""Дискретна модель 10 печей, спільної черги та зміни кількості увімкнених печей."""

from datetime import datetime
import argparse
import csv
import json
from collections import deque
from pathlib import Path

from generator import CLOSE_HOUR, OPEN_HOUR, ROOT, STEP_MINUTES, load_orders, read_catalog # Часові параметри краще брати з run.py, а не з генератора
END_HOUR = 24
QUEUE_LIMIT = 10

"""Завантажує результати симуляції з JSON-файлу. Це для інших модулів."""
def load_simulation(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

"""Перетворює розклад перемикань на погодинний масив кількості печей з 9 до 21."""
def parse_schedule(source):
    if isinstance(source, str):
        changes = {}
        for part in source.replace(';', ',').split(','):
            if not part.strip():
                continue
            hour, count = map(int, part.strip().split(':', 1))
            changes[hour] = count
    else:
        changes = {int(h): int(n) for h, n in source.items()}

    if not changes:
        raise ValueError('Розклад не може бути порожнім.')

    if min(changes) >= OPEN_HOUR:
        raise ValueError('Перше перемикання має бути раніше 9:00.')

    if any(n < 1 for n in changes.values()):
        raise ValueError('Кількість печей має бути більшою за 1')

    hourly = []
    count = changes[max(h for h in changes if h < OPEN_HOUR)] # найближче зліва від початку

    for hour in range(OPEN_HOUR, CLOSE_HOUR):
        if hour in changes:
            count = changes[hour]
        hourly.append(count)

    return tuple(hourly)


"""Перетворює погодинний масив кількості печей на текстовий розклад для аналізатора."""
def schedule_text(hourly):
    return ', '.join(
        f'{hour}: {hourly[hour - OPEN_HOUR]}'
        for hour in range(OPEN_HOUR, CLOSE_HOUR)
    )


"""Попередньо обчислює тривалість за каталогами, щоб симуляція була швидкою."""
def prepare_orders(orders, recipes, toppings):
    prepared = []
    seen_ids = set()
    for order in orders:
        order_id = int(order['id'])
        minute = int(order['minute'])

        if order_id in seen_ids:
            raise ValueError(f'Повторюваний ID замовлення: {order_id}')

        # Замовлення поза часовими межами ми не відхиляємо, симуляція його просто не розгляне.

        recipe = recipes[str(order['recipe_id'])]
        extra_time = sum(toppings[str(item_id)]['time'] for item_id in order['toppings'])
        duration = recipe['time'] + extra_time
        if duration <= 0:
            raise ValueError(f'Некоректна тривалість замовлення: {order_id}')

        prepared.append((minute, order_id, duration))
        seen_ids.add(order_id)
    return sorted(prepared, key=lambda item: (item[0], item[1])) # Тут усе-таки додано сортування за часом, але там і так усе відсортовано


"""Симуляція: печі працюють - працює черга - нові замовлення - намагаємося розмістити замовлення в печах
і так по колу.

При зменшенні кількості печей зайняті печі завершують приготування та вимикаються.
Поза часовими межами замовлення не розглядаються.
Повертаємо масив часу роботи у хвилинах для кожної печі та масив статусів *розглянутих* замовлень (прийнято/відхилено).
Черга за принципом FIFO.
"""
def simulate(prepared_orders, hourly_schedule):
    if len(hourly_schedule) != CLOSE_HOUR - OPEN_HOUR:
        raise ValueError('Некоректна довжина погодинного розкладу.')
    if any(not 1 <= count for count in hourly_schedule):
        raise ValueError('Кількість печей має бути не меншою за 1.')

    remaining = [0.0] * max(hourly_schedule)
    cooking_id = [None] * len(remaining)
    oven_minutes = [0.0] * len(remaining)
    queue = deque()
    statuses = []
    status_by_id = {}
    timeline = []
    pointer = 0
    while pointer < len(prepared_orders) and prepared_orders[pointer][0] < OPEN_HOUR * 60:
        pointer += 1

    for minute in range(OPEN_HOUR * 60, END_HOUR * 60 + 1, STEP_MINUTES): # Симулюємо залишок дня до END_HOUR, щоб завершити всю чергу.
        target = hourly_schedule[min(minute // 60 - OPEN_HOUR, len(hourly_schedule) - 1)]

        # Виконуємо приготування протягом наступних 5 хвилин.
        if minute > OPEN_HOUR * 60: # першу ітерацію ігноруємо
            for oven in range(len(remaining)):
                # піч вимикається за графіком, але якщо кінець дня, то вимикаємо лише за умови порожньої черги
                enabled = oven < target and (minute < CLOSE_HOUR * 60 or len(queue) > 0)

                if enabled:
                    oven_minutes[oven] += STEP_MINUTES
                else:
                    if cooking_id[oven] is not None:
                        oven_minutes[oven] += min(STEP_MINUTES, remaining[oven])
                    else:
                        continue

                remaining[oven] = max(-STEP_MINUTES, remaining[oven] - STEP_MINUTES)
                if remaining[oven] <= 0 and cooking_id[oven] is not None:
                    status_by_id[cooking_id[oven]]['completion_minute'] = minute + remaining[oven]
                    cooking_id[oven] = None

                if cooking_id[oven] is None:
                    if len(queue) > 0 and enabled:
                        order_id, duration = queue.popleft()
                        cooking_id[oven] = order_id
                        # Враховуємо час, який ми чекали після завершення, як час, який можемо витратити на приготування:
                        remaining[oven] += duration
                        # Якщо час на замовлення раптом менший за STEP_MINUTES, то зменшувати треба STEP_MINUTES, а не змінювати функціонал.

        # Приймаємо всі замовлення, що надійшли в поточний момент.
        if minute < CLOSE_HOUR * 60: # Ну, якщо ми ще не закрилися
            while pointer < len(prepared_orders) and prepared_orders[pointer][0] <= minute:
                if(prepared_orders[pointer][0]) != minute:
                    pointer += 1
                    continue
                _, order_id, duration = prepared_orders[pointer]
                pointer += 1

                accepted = len(queue) < QUEUE_LIMIT

                if accepted:
                    if all(cooking_id[oven] is not None for oven in range(target)): # Якщо всі печі зайняті (тобто черга не порожня)
                        if len(queue) < QUEUE_LIMIT:
                            queue.append((order_id, duration)) # Додаємо до черги, якщо не перевищуємо ліміт
                    else:
                        for oven in range(target): # Інакше відразу призначаємо піч, але без додавання від'ємного remaining.
                            if cooking_id[oven] is None:
                                cooking_id[oven] = order_id
                                remaining[oven] = duration
                                break

                status = {
                    'id': order_id,
                    'accepted': accepted,
                    'completion_minute': None,
                }
                statuses.append(status)
                status_by_id[order_id] = status

        # Зберігаємо фактичну довжину черги після обробки поточного кроку.
        timeline.append([minute, len(queue)])

        if minute >= CLOSE_HOUR * 60:
            if not queue and all(order_id is None for order_id in cooking_id):
                break

    return oven_minutes, statuses, timeline


"""Зберігає результати симуляції в один JSON-файл для аналізатора."""
def save_simulation(oven_minutes, statuses, hourly_schedule, generation_path, timeline,
                    folder=ROOT / 'output' / 'simulated'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True) # Створюємо папку, якщо її ще немає

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path = folder / f'Simulator_{stamp}_{Path(generation_path).stem}_results.json'

    result = {
        'generation': Path(generation_path).name,
        'schedule': list(hourly_schedule),
        'oven_minutes': oven_minutes,
        'total_oven_minutes': sum(oven_minutes),
        'total_orders': len(statuses),
        'accepted': sum(order['accepted'] for order in statuses),
        'rejected': sum(not order['accepted'] for order in statuses),
        'completed': sum(order['completion_minute'] is not None for order in statuses),
        'orders': statuses,
        'timeline': timeline,
    }

    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Симуляція піцерії за готовим JSON.')
    parser.add_argument('orders', type=Path, help='JSON замовлень')
    parser.add_argument('--schedule', default='8:2, 12:5, 18:8, 21:3')
    args = parser.parse_args()

    recipes = read_catalog(ROOT / 'data' / 'recipes.csv')
    toppings = read_catalog(ROOT / 'data' / 'toppings.csv')

    prepared = prepare_orders(load_orders(args.orders), recipes, toppings)
    hourly_schedule = parse_schedule(args.schedule)

    oven_minutes, statuses, timeline = simulate(prepared, hourly_schedule)

    path = save_simulation(
        oven_minutes, statuses, hourly_schedule, args.orders, timeline
    )

















































































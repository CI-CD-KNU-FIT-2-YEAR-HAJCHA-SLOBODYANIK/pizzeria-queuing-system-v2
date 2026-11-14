"""Аналіз результатів симуляції (з однією піччю), побудова графіків відосно N_ЗАКАЗІВ."""

import numpy as np
from scipy.signal import savgol_filter

from generator import ROOT, load_orders, read_catalog
from simulator_v1 import load_simulation


"""Обчислює виручку за завершені замовлення"""
def revenue_for_results(orders, statuses, recipes, toppings):
    accepted_ids = {
        int(row['id']) for row in statuses
        if row['accepted'] and row['completion_minute'] is not None
    }
    return sum(
        recipes[str(order['recipe_id'])]['price'] +
        sum(toppings[str(topping_id)]['price'] for topping_id in order['toppings'])
        for order in orders if int(order['id']) in accepted_ids
    )


"""Малює лінію з ковзним середнім і, за потреби, точки."""
def smooth_line(ax, x, y, color, label, show_points=True,
                point_size=22, point_alpha=0.8, line_alpha=0.4,
                line_zorder=2, point_zorder=4):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    unique_x, indices = np.unique(x, return_inverse=True) # для всіх наявних унікальних Х
    unique_y = np.bincount(indices, weights=y) / np.bincount(indices) # обчислюємо середнє Y — сума, поділена на кількість

    count = len(unique_x)
    radius = count // 10  # обчислюємо радіус динамічно

    if radius > 0:
        smooth_y = savgol_filter(  # згладжуємо бібліотечною функцією ковзного вікна
            unique_y,
            window_length=2 * radius + 1,
            polyorder=1,
            mode='interp'
        )
    else:
        smooth_y = unique_y

    ax.plot(
        unique_x, smooth_y,
        color=color,
        linewidth=2.2,
        alpha=line_alpha,
        label=label,
        zorder=line_zorder
    )

    if show_points: # за потреби також малюємо точки
        ax.scatter(
            x, y,
            color=color,
            s=point_size,
            alpha=point_alpha,
            zorder=point_zorder
        )


"""Отримує шляхи генерацій і симуляцій, виводить статистику текстом та у вигляді графіків."""
def analyze_runs(records, hourly_oven_price,
                 recipes_path=ROOT / 'data' / 'recipes.csv',
                 toppings_path=ROOT / 'data' / 'toppings.csv'):

    if not records:
        raise ValueError('Потрібні результати прогонів')

    recipes = read_catalog(recipes_path)
    toppings = read_catalog(toppings_path)
    rows = []

    for record in records:
        orders = load_orders(record['generation'])
        result = load_simulation(record['simulation'])

        statuses = result['orders']

        source_ids = {int(order['id']) for order in orders}
        status_ids = {int(order['id']) for order in statuses}

        if not status_ids <= source_ids:
            raise ValueError(f'Невідомі ID замовлень у {record["simulation"]}')

        gross = revenue_for_results(orders, statuses, recipes, toppings) # Обчислюємо виручку
        oven_minutes = float(result['total_oven_minutes'])
        oven_cost = oven_minutes / 60 * hourly_oven_price

        # Можлива виручка від усіх створених замовлень без вирахування витрат.
        possible_gross = sum(
            recipes[str(order['recipe_id'])]['price'] +
            sum(toppings[str(topping_id)]['price'] for topping_id in order['toppings'])
            for order in orders
        )

        rows.append({
            'count': len(orders),
            'accepted': sum(bool(order['accepted']) for order in statuses),
            'rejected': sum(not order['accepted'] for order in statuses),
            'completed': sum(order['completion_minute'] is not None for order in statuses),
            'gross': gross,
            'possible_gross': possible_gross,
            'oven_minutes': oven_minutes,
            'oven_cost': oven_cost,
            'net': gross - oven_cost,
        })

    rows.sort(key=lambda row: row['count'])

    print('\nРЕЗУЛЬТАТИ СИМУЛЯЦІЙ (1 ПІЧ)')
    print(f'{"Створено":>9} {"Прийнято":>9} {"Відмов":>8} {"Готово":>8} '
          f'{"Виручка":>12} {"Витрати":>12} {"Прибуток":>12}')

    for row in rows:
        print(f'{row["count"]:>9} {row["accepted"]:>9} {row["rejected"]:>8} '
              f'{row["completed"]:>8} {row["gross"]:>12.2f} '
              f'{row["oven_cost"]:>12.2f} {row["net"]:>12.2f}')

    mean_net = sum(row['net'] for row in rows) / len(rows)
    print(f'Середній чистий прибуток: {mean_net:.2f} грн')
    print('Виручка розраховується за прийняті та завершені замовлення.')

    # Далі — ГРАФІКИ
    import matplotlib.pyplot as plt

    x = [row['count'] for row in rows]

    # Графік 1. Виручка, чистий прибуток та можлива виручка.
    fig, ax = plt.subplots(figsize=(10, 5.5))

    gross = [row['gross'] for row in rows] # виручка
    net_visible = [max(0, row['net']) for row in rows] # чистий прибуток
    possible_gross_visible = [row['possible_gross'] for row in rows] # теоретична виручка

    # Жовта лінія та точки розташовані на задньому плані.
    smooth_line(
        ax, x, possible_gross_visible,
        color='#e5ae00',
        label='Можлива виручка',
        show_points=True,
        point_size=24,
        point_alpha=0.45,
        line_alpha=0.25,
        line_zorder=1,
        point_zorder=1.5
    )

    # Синя лінія та точки — фактична виручка.
    smooth_line(
        ax, x, gross,
        color='#0756c8',
        label='Виручка',
        show_points=True,
        point_size=24,
        point_alpha=0.95,
        line_alpha=0.35
    )

    # Червона лінія — чистий прибуток, без точок.
    smooth_line(
        ax, x, net_visible,
        color='#d63838',
        label='Чистий прибуток',
        show_points=False,
        line_alpha=0.55
    )

    ax.set(
        title='Виручка та чистий прибуток',
        xlabel='Кількість створених замовлень',
        ylabel='Гривні (грн)'
    )
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    # Графік 2. Відмовлені та завершені замовлення.
    fig, ax = plt.subplots(figsize=(10, 5.5))

    smooth_line(
        ax, x,
        [row['count'] - row['completed'] for row in rows],
        color='#c44e2b',
        label='Відмовлено',
        show_points=True,
        point_size=24,
        point_alpha=0.95,
        line_alpha=0.4
    )

    smooth_line(
        ax, x,
        [row['completed'] for row in rows],
        color='#2b9348',
        label='Завершено',
        show_points=True,
        point_size=24,
        point_alpha=0.95,
        line_alpha=0.4
    )

    ax.set(
        title='Обробка замовлень',
        xlabel='Кількість створених замовлень',
        ylabel='Кількість замовлень'
    )
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    # Графік 3. Час роботи печі.
    fig, ax = plt.subplots(figsize=(10, 5.5))

    smooth_line(
        ax, x,
        [row['oven_minutes'] / 60 for row in rows],
        color='#7b2cbf',
        label='Час роботи',
        show_points=True,
        point_size=24,
        point_alpha=0.95,
        line_alpha=0.4
    )

    ax.set(
        title='Час роботи печі',
        xlabel='Кількість створених замовлень',
        ylabel='Години роботи'
    )
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend()

    fig.tight_layout()

    plt.show(block=False)

    return rows
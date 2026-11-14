"""Аналіз результатів симуляції (з однією піччю), побудова графіків відносно ЧАСУ."""

import numpy as np

from generator import OPEN_HOUR, ROOT, STEP_MINUTES, load_orders, read_catalog
from simulator_v1 import END_HOUR, load_simulation, prepare_orders


"""Обчислює часові показники одного прогону."""
def timeline_for_run(orders, statuses, recipes, toppings, minutes):
    orders_by_id = {int(order['id']): order for order in orders}
    durations = {
        order_id: duration
        for _, order_id, duration in prepare_orders(orders, recipes, toppings)
    }

    accepted_times = []
    started_times = []
    completed_times = []
    rejected_times = []

    next_free = OPEN_HOUR * 60

    for status in statuses:
        order_id = int(status['id'])
        arrival = int(orders_by_id[order_id]['minute']) # время поступления заказа

        if status['accepted']:
            start = max(arrival, next_free)
            next_free = start + durations[order_id]

            accepted_times.append(arrival)
            started_times.append(start)

            if status['completion_minute'] is not None:
                completed_times.append(float(status['completion_minute']))
            else:
                rejected_times.append(arrival) # можно и (END_HOUR * 60) 
        else:
            rejected_times.append(arrival)

    # Обчислюємо накопичену кількість подій до кожного моменту часу.
    def cumulative(values):
        values = np.sort(np.asarray(values, dtype=float))
        return np.searchsorted(values, minutes, side='right')

    completed = cumulative(completed_times)
    rejected = cumulative(rejected_times)
    queue = cumulative(accepted_times) - cumulative(started_times)

    return completed, rejected, queue


"""Отримує шляхи генерацій і симуляцій, виводить часові графіки."""
def analyze_timeline_runs(records,
                          recipes_path=ROOT / 'data' / 'recipes.csv',
                          toppings_path=ROOT / 'data' / 'toppings.csv'):

    if not records:
        raise ValueError('Потрібні результати прогонів')

    recipes = read_catalog(recipes_path)
    toppings = read_catalog(toppings_path)
    rows = []

    minutes = np.arange(
        OPEN_HOUR * 60,
        END_HOUR * 60 + 1,
        STEP_MINUTES
    )

    for record in records:
        orders = load_orders(record['generation'])
        result = load_simulation(record['simulation'])

        statuses = result['orders']

        source_ids = {int(order['id']) for order in orders}
        status_ids = {int(order['id']) for order in statuses}

        if not status_ids <= source_ids:
            raise ValueError(f'Невідомі ID замовлень у {record["simulation"]}')

        completed, rejected, queue = timeline_for_run(
            orders, statuses, recipes, toppings, minutes
        )

        rows.append({
            'count': len(orders),
            'completed': completed,
            'rejected': rejected,
            'queue': queue,
        })

    # Обчислюємо середні значення за всіма прогонами.
    avg_orders = sum(row['count'] for row in rows) / len(rows)

    completed = np.mean([row['completed'] for row in rows], axis=0)
    rejected = np.mean([row['rejected'] for row in rows], axis=0)
    queue = np.mean([row['queue'] for row in rows], axis=0)

    # Ну і ось ГРАФІКИ
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    x = minutes

    completed_step = np.diff(completed, prepend=0)
    rejected_step = np.diff(rejected, prepend=0)

    title_suffix = (f'середнє за {len(rows)} прогонами')

    # Графік 1. Завершені та відхилені замовлення, довжина черги.
    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.bar(
        x, completed_step,
        width=STEP_MINUTES,
        color="#20bd42",
        label='Завершено'
    )

    ax.bar(
        x, rejected_step,
        bottom=completed_step,
        width=STEP_MINUTES,
        color="#e60000",
        label='Відмовлено'
    )

    ax.set(
        title=f'Замовлення за інтервалами часу — {title_suffix}, середня кількість замовлень: {avg_orders:g}',
        xlabel='Час',
        ylabel='Кількість замовлень за 5 хвилин'
    )

    ax.set_ylim(bottom=0)
    ax.set_xlim(x[0], x[-1])
    ax.set_xticks(np.arange(x[0], x[-1] + 1, 60))
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, pos: f'{int(value // 60):02d}:{int(value % 60):02d}')
    )
    ax.tick_params(axis='x', rotation=45)
    ax.grid(alpha=0.25)

    # Довжина черги на окремій шкалі від 0 до 10.
    ax_queue = ax.twinx()

    ax_queue.plot(
        x, queue,
        color="#1A23A1",
        linewidth=2,
        drawstyle='steps-post',
        label='Довжина черги'
    )

    ax_queue.set_ylabel('Довжина черги')
    ax_queue.set_ylim(0, 10)
    ax_queue.set_yticks(np.arange(0, 11, 2))

    # Об'єднуємо позначення стовпців і лінії в одну легенду.
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax_queue.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc='upper left')

    fig.tight_layout()

    plt.show(block=False)

    return {
        'minutes': minutes,
        'completed': completed,
        'rejected': rejected,
        'queue': queue,
    }

"""Запуск генерацій і симуляцій з декількома печами."""

import time

from analyzer_v2 import analyze_runs
from analyzer_ovens import analyze_ovens
from analyzer_timeline_v2 import analyze_timeline_runs
from generator import ROOT, generate_orders, read_catalog, save_orders
from simulator_v2 import (
    parse_schedule,
    prepare_orders,
    save_simulation,
    schedule_text,
    simulate,
)


DEFAULTS = {
    'min_orders': 20,
    'max_orders': 500,
    'runs': 100,
    'seed': time.time_ns(),
    'oven_price': 180.0,
    'custom_probability': 0.35,
    'repeat_topping_probability': 0.45,
    'schedule': '8:1, 12:3, 15:2, 18:4, 21:2',
}


"""Створює серію замовлень, запускає симулятор і повертає шляхи JSON."""
def run_experiment(settings, progress=print, compare=False):
    low = settings['min_orders']
    high = settings['max_orders']
    runs = settings['runs']

    if low < 0 or high < low or runs < 1:
        raise ValueError('Некоректна кількість замовлень або прогонів.')

    for key in ('custom_probability', 'repeat_topping_probability'):
        if not 0 <= settings[key] <= 1:
            raise ValueError(f'{key} має бути в діапазоні від 0 до 1.')

    counts = ([low] if runs == 1 else
              [round(low + (high - low) * i / (runs - 1)) for i in range(runs)])

    recipes = read_catalog(ROOT / 'data' / 'recipes.csv')
    toppings = read_catalog(ROOT / 'data' / 'toppings.csv')
    records = []

    progress(f'Замовлення за прогонами: {counts}')
    progress(f'Початковий seed: {settings["seed"]}; кожний наступний +1')

    if compare:
        progress('Порівняння 1–10 печей без розкладу: 10 симуляцій на одну генерацію')
    else:
        progress(f'Розклад печей: {schedule_text(parse_schedule(settings["schedule"]))}')

    for index, count in enumerate(counts):
        orders = generate_orders(
            count,
            seed=settings['seed'] + index, # Початковий seed + індекс прогону
            custom_probability=settings['custom_probability'],
            repeat_topping_probability=settings['repeat_topping_probability'],
        )

        generation_path = save_orders(orders)
        prepared = prepare_orders(orders, recipes, toppings)

        # Тут и компаре и не компаре ну в общем общий цикл. Если не компаре то одна итерация.
        for oven_count in (range(1, 11) if compare else [None]):
            hourly_schedule = parse_schedule(
                f'0:{oven_count}' if compare else settings['schedule']
            )

            oven_minutes, statuses, timeline = simulate(prepared, hourly_schedule)

            simulation_path = save_simulation(
                oven_minutes, statuses, hourly_schedule, generation_path, timeline
            )

            record = {
                'generation': generation_path,
                'simulation': simulation_path
            }

            if compare:
                record.update({'run_index': index, 'ovens': oven_count})

            records.append(record)

            if not compare:
                progress(f'Прогін {index + 1}/{runs}: {count} замовлень; '
                         f'прийнято {sum(row["accepted"] for row in statuses)}, '
                         f'відмовлено {sum(not row["accepted"] for row in statuses)}')

        if compare:
            progress(f'Прогін {index + 1}/{runs}: {count} замовлень; 10 симуляцій')

    return records


"""Графічний інтерфейс запуску симуляцій."""
def launch_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title('Піцерія. Етап 2 — декілька печей')
    root.geometry('650x550')

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)

    ttk.Label(
        frame,
        text='Моделювання роботи декількох печей',
        font=('Segoe UI', 14, 'bold')
    ).pack(anchor='w', pady=(0, 10))

    fields = {}
    form = ttk.Frame(frame)
    form.pack(fill='x')

    labels = {
        'min_orders': 'Мінімум замовлень',
        'max_orders': 'Максимум замовлень',
        'runs': 'Кількість прогонів',
        'seed': 'Початковий seed',
        'oven_price': 'Вартість однієї печі (грн/год)',
        'custom_probability': 'Імовірність індивідуальної піци',
        'repeat_topping_probability': 'Імовірність наступного топінгу',
        'schedule': 'Розклад печей (година:кількість)',
    }

    # Створюємо поля введення за допомогою циклу.
    for i, (key, label) in enumerate(labels.items()):
        ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=4)

        entry = ttk.Entry(form, width=27)
        entry.insert(0, str(DEFAULTS[key]))
        entry.grid(row=i, column=1, sticky='ew', padx=(16, 0), pady=4)

        fields[key] = entry

    form.columnconfigure(1, weight=1)

    log = tk.Text(frame, height=10, wrap='word', state='normal')
    log.pack(side='bottom', fill='both', expand=True, pady=(12, 0))

    # Виводимо повідомлення в консоль і графічний інтерфейс.
    def progress(message):
        log.insert('end', str(message) + '\n')
        log.see('end')
        root.update_idletasks()
        print(message)

    def start(timeline=False, compare=False):
        try:
            settings = {
                'min_orders': int(fields['min_orders'].get()),
                'max_orders': int(fields['max_orders'].get()),
                'runs': int(fields['runs'].get()),
                'seed': int(fields['seed'].get()),
                'oven_price': float(fields['oven_price'].get().replace(',', '.')),
                'custom_probability': float(fields['custom_probability'].get().replace(',', '.')),
                'repeat_topping_probability': float(fields['repeat_topping_probability'].get().replace(',', '.')),
                'schedule': fields['schedule'].get(),
            }

            records = run_experiment(settings, progress, compare=compare)

            if compare:
                analyze_ovens(records, settings['oven_price'])

            elif timeline:
                analyze_timeline_runs(records)
                progress(f'Часовий аналіз виконано для {len(records)} прогонів.')
            else:
                rows = analyze_runs(records, settings['oven_price'])

                progress(f'Середній чистий прибуток: '
                         f'{sum(row["net"] for row in rows) / len(rows):.2f} грн')

        except Exception as exc:
            messagebox.showerror('Помилка', str(exc))

    buttons = ttk.Frame(frame)
    buttons.pack(anchor='w', pady=(12, 0))

    button = ttk.Button(
        buttons,
        text='Графіки за кількістю',
        command=start
    )
    button.pack(side='left', padx=(0, 8))

    timeline_button = ttk.Button(
        buttons,
        text='Графіки за часом',
        command=lambda: start(timeline=True)
    )
    timeline_button.pack(side='left', padx=(0, 8))

    compare_button = ttk.Button(
        buttons,
        text='Порівняння 1–10 печей',
        command=lambda: start(compare=True)
    )
    compare_button.pack(side='left')

    root.mainloop()


if __name__ == '__main__':
    launch_gui()




















































































"""Python 3.10+. No external dependencies. See generate() input contract."""
import argparse
import json
import random
import time
from itertools import combinations


def generate(data, event='fight_night', seed=None, timeout=10):
    if event not in ('fight_night', 'ppv'):
        raise ValueError('event: fight_night или ppv')
    if data.get('history_complete') is not True:
        raise ValueError('Нужна полная история встреч: history_complete=true')
    roster = data['fighters']
    ids = [f['id'] for f in roster]
    if len(set(ids)) != len(ids):
        raise ValueError('Повторяющиеся ID бойцов')
    positions = set()
    for f in roster:
        for key in ('name', 'division'):
            if not isinstance(f[key], str) or not f[key].strip():
                raise ValueError(f'Некорректное поле {key}')
        for key in ('wins', 'losses'):
            if type(f[key]) is not int or f[key] < 0:
                raise ValueError(f'Некорректный рекорд: {f["name"]}')
        for key in ('active', 'available', 'champion'):
            if type(f[key]) is not bool:
                raise ValueError(f'Поле {key} должно быть boolean')
        r = f['rank']
        if r is not None and (type(r) is not int or not 1 <= r <= 15):
            raise ValueError('rank: null или целое 1..15')
        if f['champion'] and r is not None:
            raise ValueError('У чемпиона rank должен быть null')
        if f['active'] and (r is not None or f['champion']):
            key = (f['division'], 'C' if f['champion'] else r)
            if key in positions:
                raise ValueError('Дублирующееся место в рейтинге')
            positions.add(key)
    history = set()
    for a, b in data['history']:
        if a == b:
            raise ValueError('Некорректная история встреч')
        history.add(frozenset((a, b)))
    fighters = [f for f in roster if f['active'] and f['available']
                and (event == 'ppv' or not f['champion'])]
    if len(fighters) < 26:
        raise ValueError('Недостаточно доступных бойцов: нужно минимум 26')
    rng = random.Random(seed)
    edges = []
    for i, j in combinations(range(len(fighters)), 2):
        a, b = fighters[i], fighters[j]
        if a['division'] != b['division']:
            continue
        if frozenset((a['id'], b['id'])) in history:
            continue
        title = a['champion'] or b['champion']
        ra, rb = a['rank'], b['rank']
        if title:
            challenger = b if a['champion'] else a
            if challenger['champion'] or challenger['rank'] not in (1, 2):
                continue
            priority = (0, challenger['rank'], 0)
        elif ra is not None and rb is not None:
            if abs(ra-rb) > 2:
                continue
            priority = (1, ra+rb, abs(ra-rb))
        elif ra is None and rb is None:
            dw, dl = abs(a['wins']-b['wins']), abs(a['losses']-b['losses'])
            if dw > 2 or dl > 2 or abs(a['wins']+a['losses']-b['wins']-b['losses']) > 3:
                continue
            priority = (2, -(a['wins']+b['wins']), dw+dl)
        else:
            continue
        mask = (1 << i) | (1 << j)
        anchor = title if event == 'ppv' else ra is not None and rb is not None and max(ra, rb) <= 5
        # Match quality first during search; prominence first for card ordering.
        quality = (priority[0], priority[2], priority[1], rng.random())
        edges.append((i, j, title, mask, anchor, priority, quality))
    edges.sort(key=lambda e: e[6])
    adjacency = [[] for _ in fighters]
    for edge in edges:
        adjacency[edge[0]].append(edge)
        adjacency[edge[1]].append(edge)
    deadline = time.monotonic() + timeout
    failed = set()

    def search(mask, needed):
        if time.monotonic() > deadline:
            raise TimeoutError('Лимит поиска; существование полного карда пока не определено')
        if needed == 0:
            return []
        if mask.bit_count() < needed*2:
            return None
        state = (mask, needed)
        if state in failed:
            return None
        options = [(i, [e for e in adjacency[i] if e[3] & mask == e[3]])
                   for i in range(len(fighters)) if mask & (1 << i)]
        viable = [(i, es) for i, es in options if es]
        if len(viable) < needed*2:
            return None
        i, es = min(viable, key=lambda item: len(item[1]))
        for e in es:
            tail = search(mask ^ e[3], needed-1)
            if tail is not None:
                return [e] + tail
        tail = search(mask & ~(1 << i), needed)
        if tail is not None:
            return tail
        failed.add(state)
        return None

    anchors = sorted((e for e in edges if e[4]), key=lambda e: (e[5], e[6]))
    if not anchors:
        raise ValueError('Нет допустимого титульного боя' if event == 'ppv' else 'Нет допустимого главного боя топ-5')
    for anchor in anchors:
        tail = search(((1 << len(fighters))-1) ^ anchor[3], 12)
        if tail is not None:
            chosen = sorted([anchor]+tail, key=lambda e: (e[5], e[6]))
            card = []
            for n, e in enumerate(chosen, 1):
                section = 'Main Event' if n == 1 else 'Co-Main Event' if n == 2 else 'Main Card' if n <= 6 else 'Prelims'
                card.append(dict(position=n, section=section, title=e[2],
                                 division=fighters[e[0]]['division'],
                                 fighters=[fighters[e[0]], fighters[e[1]]]))
            return dict(event=event, seed=seed, fights=card)
    raise ValueError('Невозможно собрать 13 боёв при заданных ограничениях')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('roster')
    p.add_argument('--event', choices=['fight_night', 'ppv'], default='fight_night')
    p.add_argument('--seed', type=int)
    p.add_argument('--timeout', type=float, default=10)
    args = p.parse_args()
    try:
        with open(args.roster, encoding='utf-8') as stream:
            result = generate(json.load(stream), args.event, args.seed, args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, TimeoutError, OSError) as error:
        p.exit(1, f'Ошибка: {error}\n')

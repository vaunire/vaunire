from typing import List

from .models import Album, Style


def get_visible_styles(album: Album, max_total_width_px: int = 180,) -> List[Style]:
    """
    Умный выбор 0–2 стилей для карточки альбома.

    Делает так, чтобы второй стиль гарантированно влезал целиком и без переноса.
    Если второй стиль «вылезает» — он вообще не показывается, сразу показываем +N.
    """

    PX_PER_CHAR = 6
    CHIP_PADDING = 16
    GAP_BETWEEN_CHIPS = 1  
    PLUS_CHIP_WIDTH = 1    

    try:
        all_styles = list(album.styles.all())
    except:
        all_styles = list(album.styles.all()[:12])

    if not all_styles:
        return []

    # Сначала короткие — шанс влезть выше
    all_styles.sort(key=lambda s: len(s.name))

    selected: List[Style] = []
    used_width = 0

    for style in all_styles:
        chip_width = len(style.name) * PX_PER_CHAR + CHIP_PADDING

        # Сколько места потребуется с учётом уже выбранных
        needed = used_width + chip_width
        if selected:
            needed += GAP_BETWEEN_CHIPS

        # Если это второй стиль — прибавляем место под будущий "+N"
        if len(selected) == 1:
            needed += GAP_BETWEEN_CHIPS + PLUS_CHIP_WIDTH

        if needed <= max_total_width_px:
            selected.append(style)
            used_width += chip_width + (GAP_BETWEEN_CHIPS if selected else 0)
        else:
            # Больше не влезет — выходим
            break

    return selected
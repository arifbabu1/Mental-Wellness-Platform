from django import template

register = template.Library()


@register.filter
def category_icon(category_key):
    """
    Maps category keys to Font Awesome icons.
    """
    icon_map = {
        'anxiety': 'brain',
        'depression': 'cloud-rain',
        'therapy': 'couch',
        'mindfulness': 'spa',
        'self-care': 'heart',
        'stress': 'bolt',
        'sleep': 'bed',
        'nutrition': 'apple-alt',
        'exercise': 'running',
        'relationships': 'users',
        'workplace': 'briefcase',
        'addiction': 'wine-bottle',
        'trauma': 'band-aid',
        'grief': 'dove',
        'bipolar': 'adjust',
        'adhd': 'bolt',
        'ptsd': 'shield-alt',
        'eating': 'utensils',
        'panic': 'heartbeat',
        'social': 'user-friends',
        'general': 'heartbeat',
    }
    return icon_map.get(category_key, 'circle')


@register.filter
def lookup(dictionary, key):
    """
    Looks up a key in a dictionary and returns the value.
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def mul(value, arg):
    """Multiply value by arg"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

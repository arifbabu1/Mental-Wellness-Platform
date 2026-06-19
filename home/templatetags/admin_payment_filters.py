from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Custom template filter to get dictionary value by key
    Usage: {{ mydict|get_item:key }}
    """
    if dictionary is None:
        return 0
    return dictionary.get(key, 0)

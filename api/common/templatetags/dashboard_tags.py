from django import template
from common.dashboard_stats import get_platform_stats

register = template.Library()


@register.simple_tag
def platform_stats():
    return get_platform_stats()

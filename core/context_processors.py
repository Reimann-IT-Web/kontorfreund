from django.conf import settings


def product(request):
    return {"product_name": settings.PRODUCT_NAME}

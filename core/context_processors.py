from django.conf import settings


def product(request):
    return {"product_name": f"{settings.PRODUCT_NAME} ({settings.PRODUCT_EDITION})"}

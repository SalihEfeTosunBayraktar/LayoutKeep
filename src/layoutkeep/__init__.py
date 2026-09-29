"""LayoutKeep: layout-preserving document translation.

The version lives here because the application reads it at runtime: the welcome screen records
which version it was shown for, so installing a new build greets the user again instead of looking
like nothing happened (which is exactly what the first 0.9.1 build did - the flag was a bare
boolean, and an update left it set).
"""

__version__ = "0.9.12"

# Uygulamanın adı ve proje adresi tek yerde; ağ istekleri ve arayüz buradan okur.
# The application's name and project address in one place; network requests and the UI read them.
__app_name__ = "LayoutKeep"
__homepage__ = "https://github.com/SalihEfeTosunBayraktar/LayoutKeep"

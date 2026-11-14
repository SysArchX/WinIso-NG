import gettext
import locale
import os

__version__ = "0.2.0"

translation = gettext.translation("winiso", os.path.dirname(__file__) + "/locale", [locale.getlocale()[0]], fallback=True)
translation.install()
i18n = translation.gettext

from zoterm.api.client import ZoteroClient
from zoterm.config import get_settings
from zoterm.services.library import LibraryService
from zoterm.tui.app import ZotermApp


def main() -> None:
    settings = get_settings()
    client = ZoteroClient(settings)
    service = LibraryService(client)
    ZotermApp(service).run()

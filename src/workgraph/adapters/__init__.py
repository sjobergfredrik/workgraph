from .base import Adapter
from .filesystem import FilesystemAdapter
from .git_log import GitAdapter
from .ics import IcsAdapter
from .imap import ImapAdapter

__all__ = ["Adapter", "FilesystemAdapter", "GitAdapter", "IcsAdapter", "ImapAdapter"]

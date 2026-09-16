"""TorrentDownload - tracks admin-initiated torrent downloads to server.

Status lifecycle:
  downloading → complete  (percentDone == 1.0)
  downloading → error     (Transmission error)
  * → removed             (admin deleted before complete)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TorrentDownload(Base):
    __tablename__ = "torrent_downloads"

    game_id:         Mapped[int | None] = mapped_column(ForeignKey("library_games.id", ondelete="SET NULL"), nullable=True)
    transmission_id: Mapped[int | None]
    info_hash:       Mapped[str | None] = mapped_column(String(64), index=True)
    status:          Mapped[str]        = mapped_column(String(16), default="downloading", index=True)
    # "downloading" | "paused" | "complete" | "error" | "removed"
    #
    # The progress monitor only looks at rows marked "downloading", which is
    # what makes "paused" hold: nothing overwrites it until somebody resumes.
    title:           Mapped[str]        = mapped_column(String(512))
    os:              Mapped[str]        = mapped_column(String(16), default="windows")
    # Target library slug the finished download should land in. NULL / "games"
    # => built-in Games library (CUSTOM folder); a folder-backed custom library
    # slug routes the files into that library's folder + membership.
    library:         Mapped[str | None] = mapped_column(String(128), nullable=True)
    download_dir:    Mapped[str]        = mapped_column(String(1024))
    percent_done:    Mapped[float]      = mapped_column(Float, default=0.0)
    total_size:      Mapped[int]        = mapped_column(BigInteger, default=0)
    rate_download:   Mapped[int]        = mapped_column(BigInteger, default=0)
    eta:             Mapped[int]        = mapped_column(default=-1)
    error_msg:       Mapped[str | None] = mapped_column(Text, nullable=True)
    # WHY, as a name rather than a sentence, so the screen can say it in the
    # reader's language. The sentence beside it stays: it is what a reader that
    # does not know the code falls back to, and what carries anything composed
    # outside this application - the daemon's own wording, a file system error.
    #
    # On the row rather than only in the event, because the tray reads the row.
    # A transfer runs for hours and the page that started it is long gone, so a
    # reason that lived only in the event would come back in English after one
    # reload.
    error_code:      Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The one value the code above needs to be read with: how much of the
    # allowance was left, or the name of the signature that stopped it. The
    # size is already on this row as `total_size`, so one field covers every
    # message that carries a figure.
    error_detail:    Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by:      Mapped[str]        = mapped_column(String(64))
    # The account behind that name. A username is for showing; the quota
    # has to be summed against something that survives a rename, and the
    # game this download becomes takes its owner from here.
    created_by_id:   Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    # Who brought it in, as opposed to who owns it now. The two are the same
    # until the owner loses the right to upload, at which point the transfer is
    # handed to the administrator who took it away and only the first column
    # moves - exactly as `library_games.uploaded_by` behaves when a game is
    # claimed. One column said both things until a transfer first had to answer
    # them separately.
    uploaded_by_id:  Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

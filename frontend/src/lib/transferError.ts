/** Why a transfer stopped, written in the reader's language.
 *
 *  Reported by the owner from his own tray: "ale czesc jest po poilsku czesc po
 *  angliesku - Blad Refused: this torrent is 62.94 GB and only 2.9...". The
 *  status label beside it is translated; the sentence was not, because the
 *  server composed it in English. That is true of this whole application, and
 *  what made it visible here is a translated word standing directly against an
 *  untranslated sentence.
 *
 *  SAME SHAPE AS `uploadResult.ts` NEXT DOOR, deliberately: the server sends a
 *  reason NAME and the one value that name is read with, and this composes the
 *  sentence. Two ways of doing the same thing is how two copies of a rule come
 *  to disagree, and this project has watched that happen more than once.
 *
 *  THE FALLBACK IS THE POINT. A reason nobody has written a sentence for yet
 *  falls through to whatever the server wrote - English, but present. That is
 *  what makes this safe to do a piece at a time: an unclassified message is no
 *  worse off than it was, and never blank. It also carries the messages that
 *  are not ours to translate at all: the daemon's own wording, a file system
 *  error, the text of an exception from a library.
 */

import { formatBytes } from '@/utils/format';

export interface TransferError {
  /** What the server wrote, in English. The fallback, and the whole message
   *  for anything composed outside this application. */
  error_msg?: string | null;
  /** The same thing under the name the ROM, URL and CHD sections use. Torrents
   *  and GOG call it `error_msg` because they are rows in a table; the other
   *  three are jobs in memory and call it `error`. One function reads both
   *  rather than the rule being written twice and drifting apart. */
  error?: string | null;
  /** The reason as a name, when the server knew one. */
  error_code?: string | null;
  /** The one value the name is read with: bytes left of the quota, or the
   *  signature that stopped it. */
  error_detail?: string | null;
  /** Already on the row for every transfer, so the size never needs sending
   *  twice. */
  total_size?: number | null;
}

/** The project's own `t`, copied from `@/i18n` rather than approximated: the
 *  second argument is either interpolation values or a fallback string, and a
 *  narrower guess here does not accept the real function. */
type Translate = (
  key: string,
  paramsOrFallback?: Record<string, string | number> | string,
) => string;

/** What a refusal looks like when the route composes one: the body beside
 *  `detail`.
 *
 *  `detail` stays a sentence, because three dialogs, the plugins, anybody with
 *  curl and every theme already on the stores print it as it is - putting the
 *  name inside it showed those themes a block of JSON (1.0.34 audit, #19). The
 *  reason name and its figures sit next to it, for a dialog that can translate.
 */
export interface AddRefusal {
  code?: string;
  message?: string;
  size?: number;
  room?: number;
  reason?: string;
  /** `already_downloading`: whether that transfer is the reader's own. */
  mine?: boolean;
  /** `already_in_library`: the game the torrent already became. */
  game_id?: number;
  title?: string;
}

/** Why adding a torrent was refused, in the reader's language.
 *
 *  Takes the error an HTTP client threw. THREE DIALOGS CALL THIS - the core's
 *  library screen, Vapor's and NEON HORIZON's - because each keeps its own copy
 *  of that dialog, and a fix in one of them was invisible to the owner twice in
 *  this release. It reaches the themes through `window.__GD__.utils`, the same
 *  door `describeUpload` goes through.
 *
 *  Every branch ends in something printable: the translated sentence, then the
 *  server's own, then a plain apology. A dialog that shows nothing after a
 *  refusal is the failure this replaces.
 */
export function describeAddRefusal(err: unknown, t: Translate): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })
    ?.response?.data;
  const detail = data?.detail;

  // The name and its figures travel BESIDE `detail`, which stays the sentence,
  // so a theme published before the names existed still prints something a
  // person can read. Asked first: a named refusal is translated even though its
  // `detail` is a perfectly good English sentence.
  const r = (typeof data?.code === 'string' ? data : {}) as AddRefusal;

  // Older routes - and every refusal in this application that has not been
  // classified yet - answer with a plain string. Show it as it is.
  if (!r.code && typeof detail === 'string' && detail.trim()) return detail;

  const fallback = (typeof detail === 'string' ? detail : r.message || '').trim();

  switch (r.code) {
    case 'quota_refused':
      return t('torrent.add_err_quota_refused', {
        size: formatBytes(r.size ?? 0),
        room: formatBytes(r.room ?? 0),
      });

    case 'daemon_refused':
      // Transmission's own words, which are nobody's to rewrite. Framed in the
      // reader's language and quoted after it - that text is the difference
      // between "rejected" and "invalid or corrupt torrent file".
      return (r.reason || '').trim()
        ? t('torrent.add_err_daemon_refused', { reason: r.reason as string })
        : t('torrent.add_err_daemon_silent');

    case 'already_added':
      // The daemon holds this torrent and nothing the reader may see explains
      // why: a game seeded for somebody's client, or a library they cannot reach.
      return t('torrent.add_err_already_added');

    case 'already_downloading':
      // Another transfer is fetching the same content, or filing it right now.
      // Their own shows up in their transfers; somebody else's becomes a game.
      return r.mine
        ? t('torrent.add_err_already_downloading_yours')
        : t('torrent.add_err_already_downloading');

    case 'already_in_library':
      // The game this torrent already became. `addRefusalGame` below hands the
      // dialog the same game, so it can offer to open it.
      return t('torrent.add_err_already_in_library', { title: r.title || '' });

    case 'url_unsupported':
    case 'url_blocked':
    case 'url_fetch_failed':
    case 'url_too_large':
      // Adding by address: the route fetches the .torrent itself, through the
      // network guard. None of these carries a figure on purpose - what the
      // other end answered is exactly what must not come back to the screen.
      return t(`torrent.add_err_${r.code}`);

    default:
      return fallback || t('torrent.add_failed', 'Failed to add torrent.');
  }
}

/** The game an add-torrent refusal points at, or null.
 *
 *  Only for `already_in_library`: the server names a game there only when the
 *  reader may see it, so a link built from this never leads to a page that
 *  answers "not found". Handed to the themes through `window.__GD__.utils`
 *  beside `describeAddRefusal`, because each skin draws its own dialog.
 */
export function addRefusalGame(err: unknown): { id: number; title: string } | null {
  const data = (err as { response?: { data?: Record<string, unknown> } })
    ?.response?.data;
  const r = (typeof data?.code === 'string' ? data : {}) as AddRefusal;
  if (r.code !== 'already_in_library' || typeof r.game_id !== 'number') return null;
  return { id: r.game_id, title: r.title || '' };
}

/** One line for the screen. Empty while there is nothing to say. */
export function describeTransferError(row: TransferError | null, t: Translate): string {
  if (!row) return '';
  const raw = (row.error_msg || row.error || '').trim();
  const code = (row.error_code || '').trim();
  if (!code) return raw;

  switch (code) {
    // ── ROM sources ──────────────────────────────────────────────────────
    // `_safe_error` on the server has sorted these five ways for as long as it
    // has existed - it was written to keep the source URL and the auth header
    // out of the message - and simply said them in English. A ROM failure with
    // no code is one of our own ValueErrors, already specific, and falls
    // through to the sentence below.
    case 'rom_http':
      // The status is the difference between "the archive is down" and "that
      // file is gone", which is why it travels beside the name.
      return t('download.err_rom_http', { status: row.error_detail || '?' });

    case 'rom_unreachable':
    case 'rom_timeout':
    case 'rom_failed':
      return t(`download.err_${code}`);

    // ── URL uploads ──────────────────────────────────────────────────────
    case 'url_virus':
      // The signature name stays as it is: it is a name, not a sentence, and
      // translating it would make it unsearchable.
      return t('download.err_url_virus', { threat: row.error_detail || '?' });

    case 'url_failed':
      // Nothing to classify - it is whatever went wrong - so the reader gets
      // the reference that ties this row to the traceback in the server log.
      return t('download.err_url_failed', { ref: row.error_detail || '?' });

    // ── CHD conversion ───────────────────────────────────────────────────
    // Seventeen places raise ChdError, grouped into six reasons somebody can
    // act on. The specific half - the archive's name, or chdman's own
    // diagnosis - is quoted after the translated sentence, which is how the
    // grouping keeps what it looks like it is throwing away.
    case 'chd_archive':
    case 'chd_source':
    case 'chd_exists':
      return t(`download.err_${code}`, { name: row.error_detail || '?' });

    case 'chd_converter':
      // chdman's own words, which are nobody's to rewrite.
      return t('download.err_chd_converter', { detail: row.error_detail || '?' });

    case 'chd_move':
      return t('download.err_chd_move');

    case 'chd_failed':
      return t('download.err_chd_failed', { ref: row.error_detail || '?' });

    // ── GOG ──────────────────────────────────────────────────────────────
    case 'gog_checksum':
    case 'gog_incomplete':
      // Both end in "download it again", and neither needs a figure: the two
      // hashes and the two sizes are on the row and in the log already, and
      // nobody acts on an MD5.
      return t(`download.err_${code}`);

    case 'gog_virus':
      return t('download.err_gog_virus', { threat: row.error_detail || '?' });

    case 'gog_failed':
      return t('download.err_gog_failed', { ref: row.error_detail || '?' });

    case 'quota_refused':
    case 'quota_stopped':
      return t(`download.err_${code}`, {
        size: formatBytes(row.total_size ?? 0),
        room: formatBytes(Number(row.error_detail ?? 0)),
      });

    case 'threat':
      // The signature name comes from clamd and stays as it is - it is a name,
      // not a sentence, and translating it would make it unsearchable.
      return t('download.err_threat', { threat: row.error_detail || '?' });

    case 'daemon':
      // Transmission's own wording, which is nobody's to rewrite. Framed in the
      // reader's language and then quoted verbatim.
      return raw ? `${t('download.err_daemon')} ${raw}` : t('download.err_daemon');

    case 'lost':
    case 'no_game':
    case 'no_folder':
    case 'no_files':
    case 'move_failed':
      return t(`download.err_${code}`);

    default:
      // A name this screen has not learned yet. The server's sentence is still
      // better than silence, and this is the branch that lets the backend
      // classify more of them without waiting for the frontend.
      return raw;
  }
}

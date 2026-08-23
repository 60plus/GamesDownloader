/**
 * The password rule, once, on this side of the wire.
 *
 * It has to agree with handler/auth/passwords.py exactly. When the two drift
 * the reader is the one who pays: the form accepts the password, the server
 * refuses it, and the refusal arrives as an untranslated English sentence
 * because the error line renders whatever `detail` the API sent.
 *
 * Five screens ask for a password - registration, the reset link, the profile
 * page, the admin create form and the admin force-reset dialog - plus the
 * first-run wizard. They all check it here.
 */

export const MIN_PASSWORD = 8

/** True when the password satisfies the rule. */
export function isPasswordOk(pw: string): boolean {
  return pw.length >= MIN_PASSWORD && /[a-zA-Z]/.test(pw) && /[0-9]/.test(pw)
}

import { ApiError } from './client'

// What to tell a person for each backend error code. Messages say what to do next.
const MESSAGES: Record<string, string> = {
  not_logged_in: 'Pick who you are to continue.',
  unknown_user: "That demo account isn't available. Pick another.",
  building_not_found: "That building isn't in Synapse.",
  table_not_found: "That table isn't in this building.",
  seat_not_found: "This seat isn't in Synapse. The QR code may be out of date.",
  seat_not_occupied: 'Sit down first — the seat needs to sense you before it can link.',
  seat_taken: 'Someone is already hosting from this seat.',
  not_linked: "You're not linked to a seat anymore.",
  already_hosting: "You're hosting right now. Stop hosting to look for a partner.",
  already_searching: 'Finish or cancel your search first.',
  no_real_hosts: 'Nobody in this group can take a request right now.',
  rate_limited: "You've sent the most requests allowed this hour. Try again later.",
  request_not_pending: 'That request has already been answered or expired.',
  search_not_active: 'This search has ended.',
  match_not_active: 'This match has ended.',
  search_not_found: "This search doesn't exist anymore.",
  request_not_found: "This request doesn't exist anymore.",
  match_not_found: "This match doesn't exist anymore.",
  not_your_search: 'That search belongs to another account.',
  not_your_request: 'That request belongs to another account.',
  not_in_match: "You're not part of that match.",
  confirm_not_due: 'Nothing to confirm right now.',
  database_unavailable: "Synapse is briefly offline. Try again in a few seconds.",
  network: "Can't reach Synapse. Check your connection.",
  bad_response: "Synapse sent something unexpected. Try again.",
  validation_error: "That didn't go through. Check what you typed and try again.",
}

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? 'Something went wrong. Try again.'
  return 'Something went wrong. Try again.'
}

export function codeOf(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null
}

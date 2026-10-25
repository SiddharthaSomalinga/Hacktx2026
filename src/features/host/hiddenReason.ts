import type { HiddenReason } from '../../api/types'

// Why a host isn't findable (FR-24..27), in words that say what happens next.
export const HIDDEN_COPY: Record<HiddenReason, string> = {
  needs_topic: "Add today's topic to become findable.",
  away: "Hidden while you're away from your seat. You'll be findable again when you sit back down.",
  muted: "Muted: you won't get new requests until you unmute.",
  table_full: 'Hidden because your table has no open seat for a partner right now.',
  in_match: "Hidden while you're in a match.",
  confirm_pending: "You've been hosting for 3 hours. Confirm you're still open to partners.",
}

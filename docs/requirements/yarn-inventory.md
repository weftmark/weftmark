# Yarn and Thread Inventory

## Overview

Users can maintain an inventory of their yarn and thread stock. Inventory can be attached to weaving projects, with consumption estimated automatically from WIF data and warping plan inputs. Users retain full control to adjust or override all estimates.

The design is inspired by the Spoolman project (used in 3D printing filament tracking) — specifically the concept of tracking individual physical units (skeins, cones, tubes) with unique IDs.

---

## Yarn Record (Product Level)

A yarn record describes a type of yarn. Multiple physical units (skeins) of the same yarn share one product record.

### Fields

| Field | Description | Example |
|---|---|---|
| Brand / Manufacturer | Producer of the yarn | Maurice Brassard |
| Product name | Name or line | Cotton Yarn |
| Weaving weight notation | Industry weight notation | 8/2 |
| Yarn weight category | Standard weight category | Lace |
| Fiber content | Material composition | 100% Cotton |
| Color name | Manufacturer color name | Natural |
| Color (hex or RGB) | Visual color reference | |
| Physical weight | Weight per unit (oz and grams) | 8.0 oz / 227g |
| Approximate yardage | Yards per unit | 1680 yds |
| Yards per pound | Standardized yardage reference | 3360 yds/lb |
| Sett recommendation | Ends per inch (epi) | 20–30 epi |
| Purchase source | Where purchased | The Woolery |
| Purchase price | Price per unit at time of purchase | |
| Purchase date | When purchased | |
| Notes | Any additional notes | |

---

## Skein / Unit Record (Physical Level)

Each physical unit of yarn (a cone, tube, skein, or ball) gets its own record with a unique ID. This allows tracking which specific physical units were used in which projects.

### Fields

| Field | Description |
|---|---|
| Unique ID | Platform-generated identifier for this physical unit |
| Yarn product | Reference to the parent yarn product record |
| Status | Available / In use / Consumed |
| Current quantity (yardage) | Remaining length in this unit |
| Current quantity (weight) | Remaining weight in this unit |
| Notes | Any notes specific to this unit |

---

## Inventory Tracking

### Quantity Units

Both weight and yardage are tracked per unit. Weavers use both units depending on context, and the two are interconvertible via the yards-per-pound value on the product record.

### Manual Adjustment

Users can manually adjust inventory at any time — for example, to record yarn used outside the platform, correct a data entry error, or account for partial skeins.

---

## Attaching Yarn to a Project

When yarn is attached to a weaving project:

1. **Estimated consumption is calculated** from:
   - WIF thread count and sett data
   - Warping plan inputs (warp length, number of items)
   - Standard weaving allowances for take-up and shrinkage

2. **The user can adjust or override** any estimated value before confirming

3. **Specific skein IDs can be assigned** to the project, recording exactly which physical units were used

4. **Deductions are applied** as warping takes place — either automatically as the user progresses through the project, or manually entered by the user

5. **Post-project notes** can record actual consumption vs estimate, helping improve future estimates

---

## Yarn Consumption Estimation

The platform estimates yarn needed using data from the WIF file and project parameters:

**Warp yarn:** Number of warp ends × total warp length (+ take-up allowance)

**Weft yarn:** Picks per inch × weaving width × woven length (+ take-up and shrinkage allowance)

Take-up and shrinkage percentages are configurable defaults that the user can adjust per project.

---

## Inventory Deduction Workflow

1. User begins warping
2. Platform shows estimated yarn consumption per color/skein
3. User confirms or adjusts amounts
4. As warping and weaving proceed, deductions are recorded against specific skein IDs
5. Skein status updates automatically (Available → In use → Consumed)
6. User can manually record additional consumption at any point

---

## Ravelry Stash Push-back

Users who create yarn records in weftmark (or who imported from Ravelry but the entry predates their Ravelry account link) can push those records back to their Ravelry stash.

### API endpoint

```http
POST /people/{username}/stash/create.json
Authorization: Bearer <oauth-token>
Body: { "yarn_id": 1, "colorway_name": "Natural", "dye_lot": "A42", "notes": "..." }
```

The existing `offline` OAuth scope covers this endpoint — no re-auth required.

### Eligibility (Tier 1 only)

A yarn is eligible for push-back when ALL of the following are true:

| Condition | Reason |
| --- | --- |
| `ravelry_yarn_id IS NOT NULL` | Ravelry must be able to identify the yarn; free-text entries have no metadata value |
| `ravelry_stash_id IS NULL` | Not already in Ravelry stash |
| `archived = false` | Active yarn only |
| `deleted_at IS NULL` | Not soft-deleted |
| `out_of_stash = false` | Still in physical possession |
| User has a linked Ravelry credential | OAuth token required |

Yarns without a `ravelry_yarn_id` (Tier 2) are not offered for push-back. They would create orphaned free-text stash entries with no yarn link, photo, or metadata. Users should link the yarn to a Ravelry yarn first.

### Field mapping

| weftmark field | Ravelry stash field | Notes |
| --- | --- | --- |
| `ravelry_yarn_id` | `yarn_id` | Required; must be set (Tier 1 condition) |
| `color_name` | `colorway_name` | Direct map |
| `notes` | `notes` | Direct map |
| — | `dye_lot` | Not currently stored in weftmark; omitted unless we add the field |
| — | `location` | Not stored in weftmark; omitted |
| — | `tag_names` | Could forward weftmark yarn tags; optional |

**Not sent:** `weight_notation`, `color_hex`, `purchase_price`, `purchase_source`, `purchase_date`, `sett_min/max`, `unit_weight_oz/g`, `yards_per_pound`. These are either weftmark-specific or read-only on the Ravelry yarn record.

**Skein quantity:** Not sent in the initial push. Ravelry tracks quantity through a separate "Pack" sub-record structure (skeins, total_yards, total_grams, shop_name, total_paid). Sending a pack requires a second API call (`/packs/create.json` or via the stash create payload). This is deferred to a phase 2 "quantity sync" feature to keep the initial push simple and reversible.

### Response handling

The `stash/create.json` response returns a full `Stash` object including the new `id`. That ID must be written back to `yarns.ravelry_stash_id` immediately. If the DB write fails after the Ravelry call succeeds, the retry guard is:

1. Before pushing, check `ravelry_stash_id IS NULL` (prevents duplicate push)
2. After push, if DB commit fails, the next sync will pull the new stash entry back and reconcile via the UPDATE path — `ravelry_stash_id` will be set on the next inbound sync

No infinite-loop risk: inbound sync identifies existing records by `ravelry_stash_id` and takes the UPDATE path, not INSERT.

### UX design

#### Badge

Show a **"not in Ravelry stash" badge** on yarn cards and the detail page for Tier 1 eligible yarns, only when the user has a linked Ravelry account. Use a small Ravelry icon with muted styling — it is a passive indicator, not a call to action.

#### Entry points

| Where | Action | Confirmation |
| --- | --- | --- |
| Yarn detail page | "Add to Ravelry stash" button | Inline — no modal; button shows spinner → success/error state |
| Yarn inventory list | "Sync N yarns to Ravelry" button (visible when N > 0) | Modal: preview list of yarn names → Cancel / Add all |

No automatic push on creation. No settings toggle. Explicit user action only.

#### Post-sync state

After a successful push:

- Badge disappears (yarn now has `ravelry_stash_id`)
- Detail page shows "In Ravelry stash" with a link to the stash entry (`https://www.ravelry.com/people/{username}/stash/{stash_id}`)
- Bulk button count decrements

### Backend changes

| File | Change |
| --- | --- |
| `ravelpy/resources/stash.py` | Add `create(username, payload)` method — `POST /people/{username}/stash/create.json` |
| `app/services/ravelry.py` | Add `push_yarn_to_stash(yarn_id, user_id, db)` — eligibility check, API call, write-back |
| `app/services/ravelry.py` | Add `push_eligible_yarns_to_stash(user_id, db)` — bulk path |
| `app/routers/ravelry.py` | Add `POST /api/ravelry/stash-push/{yarn_id}` endpoint |
| `app/routers/ravelry.py` | Add `POST /api/ravelry/stash-push/bulk` endpoint |
| `app/routers/yarn.py` | Expose `ravelry_stash_id` in the yarn summary/detail response schema |

### Frontend changes

| File | Change |
| --- | --- |
| `api/ravelry.ts` | Add `pushYarnToStash(yarnId)` and `pushBulkToStash()` |
| `components/yarn/YarnCard.tsx` | Add Ravelry badge (conditional on eligibility + connected) |
| `pages/YarnDetailPage.tsx` | Add "Add to Ravelry stash" button + post-sync link |
| `pages/YarnPage.tsx` | Add "Sync N yarns to Ravelry" button + confirmation modal |
| `locales/*/translation.json` | i18n keys for all new strings (5 languages) |

### Validation plan

| Test | Method |
| --- | --- |
| `test_push_yarn_to_stash` | Happy path: `ravelry_stash_id` written back, `stash/create` called once |
| `test_push_yarn_already_synced` | Yarn with `ravelry_stash_id` set → 409 or no-op, no second Ravelry call |
| `test_push_yarn_not_tier1` | `ravelry_yarn_id IS NULL` → 422 rejected |
| `test_push_yarn_archived` | `archived=True` → 422 rejected |
| `test_push_yarn_no_credential` | No OAuth credential → 404 |
| `test_bulk_push` | Only Tier 1 yarns included; count returned matches |
| `test_bulk_push_empty` | No eligible yarns → 200 with count=0, no API calls |
| UI smoke | Badge visible on Tier 1 yarn, absent after push; bulk button count correct |

### Estimate

| Area | Hours |
| --- | --- |
| Backend (service + endpoints + ravelpy method) | 3–5 |
| Frontend (badge + detail button + bulk modal + i18n) | 4–6 |
| Tests | 2–3 |
| **Total** | **9–14** |

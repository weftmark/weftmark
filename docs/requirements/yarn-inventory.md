# Yarn and Thread Inventory

## Overview

Users can maintain an inventory of their yarn and thread stock. Inventory can be attached to weaving activities, with consumption estimated automatically from WIF data and warping plan inputs. Users retain full control to adjust or override all estimates.

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

Each physical unit of yarn (a cone, tube, skein, or ball) gets its own record with a unique ID. This allows tracking which specific physical units were used in which activities.

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

## Attaching Yarn to an Activity

When yarn is attached to a weaving activity:

1. **Estimated consumption is calculated** from:
   - WIF thread count and sett data
   - Warping plan inputs (warp length, number of items)
   - Standard weaving allowances for take-up and shrinkage

2. **The user can adjust or override** any estimated value before confirming

3. **Specific skein IDs can be assigned** to the activity, recording exactly which physical units were used

4. **Deductions are applied** as warping takes place — either automatically as the user progresses through the activity, or manually entered by the user

5. **Post-activity notes** can record actual consumption vs estimate, helping improve future estimates

---

## Yarn Consumption Estimation

The platform estimates yarn needed using data from the WIF file and activity parameters:

**Warp yarn:** Number of warp ends × total warp length (+ take-up allowance)

**Weft yarn:** Picks per inch × weaving width × woven length (+ take-up and shrinkage allowance)

Take-up and shrinkage percentages are configurable defaults that the user can adjust per activity.

---

## Inventory Deduction Workflow

1. User begins warping
2. Platform shows estimated yarn consumption per color/skein
3. User confirms or adjusts amounts
4. As warping and weaving proceed, deductions are recorded against specific skein IDs
5. Skein status updates automatically (Available → In use → Consumed)
6. User can manually record additional consumption at any point

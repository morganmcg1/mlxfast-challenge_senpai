#!/usr/bin/env bash
# R118-A main campaign.  Three block-randomised sessions, one model-holding
# process at a time, no GPU-profile hook anywhere (SPLIT=0 ranking rule).
#
#   orderA / orderB  the shared-expert gate+up QMV question, arms
#                    {0 ship, 1 ctl, 2 d2, 3 d1}, TEN blocks each, every block
#                    an independent random permutation of the four arms.
#                    ORDER_B is the exact time-reversal of ORDER_A, so the
#                    mean run index of every arm over the pair is identical
#                    (39/2 each) and any monotone session drift cancels.
#                    The two orders are analysed and reported SEPARATELY.
#   control          the positive control on the routed gate+up QMV, arms
#                    {0 ship, 4 rctl, 5 rd2, 6 rd1}, six blocks.  rd2/rd1
#                    remove ~174/~261 MB per decode step; if the rig does not
#                    see those, it cannot see anything and the shared-QMV null
#                    is uninterpretable.
#
# Run cost is dominated by the ~41 s model load, not by the decode itself, so
# blocks are cheap and steps are cheap: 160 steps costs 1.3 s on top of a 41 s
# load.  Ten blocks x 160 steps = 1600 raw samples per arm per order.
set -u
cd "$(dirname "$0")/../.."
D=research/maple-tanjiro-r118/evidence
S="${1:-160}"

# python3 -c "import random;r=random.Random(118);
#             print(''.join(''.join(r.sample('0123',4)) for _ in range(10)))"
ORDER_A=1302201302131203132002133102130201321032
ORDER_B=2301231020312013312002313021312031022031
ORDER_C=405650644056456045604605

echo "##### R118-A orderA $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_A}" "${D}/orderA" "${S}"
echo "##### R118-A control $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_C}" "${D}/control" "${S}"
echo "##### R118-A orderB $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_B}" "${D}/orderB" "${S}"
echo "##### R118-A done $(date -u +%H:%M:%S)"

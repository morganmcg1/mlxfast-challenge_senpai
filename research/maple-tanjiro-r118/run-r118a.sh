#!/usr/bin/env bash
# R118-A main campaign.  Three block-randomised sessions, one model-holding
# process at a time, no GPU-profile hook anywhere (SPLIT=0 ranking rule).
#
#   orderA / orderB  the shared-expert gate+up QMV question, arms
#                    {0 ship, 1 ctl, 2 d2, 3 d1}, six blocks each.  ORDER_B is
#                    the element-wise mirror of ORDER_A under 0<->3, 1<->2 and
#                    is analysed and reported SEPARATELY.
#   control          the positive control on the routed gate+up QMV, arms
#                    {0 ship, 4 rctl, 5 rd2, 6 rd1}, three blocks.  rd2/rd1
#                    remove ~163/~245 MB per decode step; if the rig does not
#                    see those, it cannot see anything and the shared-QMV null
#                    is uninterpretable.
set -u
cd "$(dirname "$0")/../.."
D=research/maple-tanjiro-r118/evidence
S="${1:-400}"

ORDER_A=012313022031321003121230
ORDER_B=321020311302012330212103
ORDER_C=045640655604

echo "##### R118-A orderA $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_A}" "${D}/orderA" "${S}"
echo "##### R118-A control $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_C}" "${D}/control" "${S}"
echo "##### R118-A orderB $(date -u +%H:%M:%S)"
research/maple-tanjiro-r118/qmv-dose-abba.sh "${ORDER_B}" "${D}/orderB" "${S}"
echo "##### R118-A done $(date -u +%H:%M:%S)"

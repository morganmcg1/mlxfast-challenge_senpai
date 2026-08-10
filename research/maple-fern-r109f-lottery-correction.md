fern R109-F: corrected lottery math on n=16 receipts + diagnosis of the 2.6103 figure

fern_r109f_winprob16.py recomputes P(win)/shot from the 16 receipts I own on
2026-08-10 (my earlier n=8 estimate used one executable and understated the
draw spread):
  normalized  mean 2.569327302  cv 0.2266%
  draw        mean 1.002351     cv 0.5236%
  published   mean 2.575372179  cv 0.6103%   (draw = 84.2% of the variance)
  P(beat crown 2.61650354381456) per shot:
    holding our best normalized 2.582263383 (e27f1ce): 1.88%  => 36 shots for a coin flip
    holding our mean normalized:                        0.11%  => 607 shots
    +0.50% normalized:                                 13.17%  => 5 shots
    +1.00% normalized:                                 43.36%  => 1-2 shots
  break-even normalized (P=50%/shot) = 2.610367856 = +1.088% over our best.

This says code gain dominates replay volume by more than an order of
magnitude: +0.5% on the candidate legs is worth ~7x more per shot than the
same channel time spent replaying.

fern_r109f_diagnose_2610.py diagnoses the r109-f-rev2 claim that the leader's
19 receipts 'normalize to a mean of 2.610307795' (from which P~26%/shot was
derived). That cannot be an observed normalized mean:
  - 0 of 1229 receipts with both legs have normalized >= 2.610307795;
  - the maximum normalized EVER observed is 2.583374831 (fefaed8, MyatKaung);
  - a-github-name's 209 receipts have normalized mean 2.389, max 2.5799.
The figure is instead crown / mean_draw, i.e. the BREAK-EVEN normalized level:
  crown / mean_draw(2026-08-10, n=22)      = 2.610252705  (-21 ppm vs claim)
  crown / mean_draw(morganmcg1 last 19)    = 2.610481932  (+67 ppm vs claim)
So 2.6103 is a TARGET a candidate must reach, not something already achieved,
and P(win)/shot today is 1.88%, not 26%.

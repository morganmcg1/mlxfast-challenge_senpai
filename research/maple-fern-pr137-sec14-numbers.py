import math

# receipt 99b71258
d = 0.0049330185546875
p = 0.000191158283203125
bd = 0.013851607421875
bp = 0.000368312662109375
dspd = 2.807937425800435
pspd = 1.9267418389503195
score = 2.55562101733798

# reference 97a5090c
R_score = 2.58882784082067
R_d = 0.0049083720703125
R_dspd = 2.82068398043601
R_pspd = 2.0014713863613727
R_ns = 2.59821630
R_nsd = 2.18184340
R_bd = 0.01384496646875

ND, NP = 0.013890, 0.0003845
ns = (ND / d) ** 0.75 * (NP / p) ** 0.25
nsd = (ND / d) ** 0.75
print("ns  %.8f  nsd %.8f  (analyzer: 2.58861777 / 2.17366255)" % (ns, nsd))

# decomposition of officialScore shortfall
ldsp = math.log(dspd / R_dspd)
lpsp = math.log(pspd / R_pspd)
print("\n--- officialScore decomposition vs 97a5090c ---")
print("total   %+.3f %%" % ((score / R_score - 1) * 100))
print("  0.75*dspd term %+.3f %%" % (0.75 * ldsp * 100))
print("  0.25*pspd term %+.3f %%" % (0.25 * lpsp * 100))
print("  sum            %+.3f %%" % ((0.75 * ldsp + 0.25 * lpsp) * 100))

# where does the pspd term come from?
R_p = R_pspd and None
# reconstruct 97a5090c candidate/baseline prefill
R_S_ms = 97.89475
R_p_tok = R_S_ms / 1000.0 / 512.0
R_bp = R_pspd * R_p_tok
print("\n--- prefill arm split ---")
print("candidate prefill  ours %.9f  ref %.9f   %+.3f %%" % (p, R_p_tok, (p / R_p_tok - 1) * 100))
print("baseline  prefill  ours %.9f  ref %.9f   %+.3f %%" % (bp, R_bp, (bp / R_bp - 1) * 100))
print("baseline  prefill  vs pinned normaliser %.7f : %+.3f %%" % (NP, (bp / NP - 1) * 100))
print("pspd shortfall %+.3f %%  == -(baseline draw) %+.3f %%" % ((pspd / R_pspd - 1) * 100, -(bp / R_bp - 1) * 100))

print("\n--- baseline decode arm (should be quiet) ---")
print("baseline decode ours %.9f  ref %.9f  %+.3f %%  [1 sigma 0.243 %%]" % (bd, R_bd, (bd / R_bd - 1) * 100))

# transfer
M4_US = 63.7
dus = (d - R_d) * 1e6
print("\n--- transfer ---")
print("candidate decode delta %+.1f us  (M4 census %.1f us)" % (dus, M4_US))
print("transfer point est %+.3f" % (-dus / M4_US))
SD_NS = 0.157
paired = SD_NS * math.sqrt(2)
EFF = 0.933
t_obs = (ns / R_ns - 1) * 100 / EFF
t_sd = paired / EFF
print("ns-based transfer %+.2f +- %.2f" % (t_obs, t_sd))
for name, v in [("pre-registered 0.50", 0.50), ("honest-band low 0.50", 0.50),
                ("honest-band high 0.75", 0.75), ("zero", 0.0), ("full 1.00", 1.0)]:
    print("   distance from %-22s %+.2f sigma" % (name, (t_obs - v) / t_sd))

print("\n--- ns band position ---")
GO, KILL = 2.6045, 2.5919
print("ns %.8f   GO %.4f  KILL %.4f" % (ns, GO, KILL))
print("ns vs GO   %+.3f %% = %+.2f sigma_paired" % ((ns / GO - 1) * 100, (ns / GO - 1) * 100 / paired))
print("ns vs KILL %+.3f %% = %+.2f sigma_paired" % ((ns / KILL - 1) * 100, (ns / KILL - 1) * 100 / paired))
print("ns vs ref  %+.3f %% = %+.2f sigma_paired" % ((ns / R_ns - 1) * 100, (ns / R_ns - 1) * 100 / paired))

print("\n--- follow-up A/B power (flip DARKBLOOM_LMHEAD_ROWMAJOR_REFINE default) ---")
sep = (0.467 - (-0.369))
print("H_preregistered ns delta %+.3f %%   H_observed %+.3f %%   separation %.3f %% = %.2f sigma"
      % (0.467, -0.369, sep, sep / paired))
pred_off = ns * (d / (d - dus / 1e6)) ** 0.75
print("if the arm is the whole +24.6 us, flipped-default ns ~= %.5f (ref %.5f)" % (pred_off, R_ns))

print("\n--- S / T ---")
S = p * 512 * 1000
T = (d - (p * 512 * 1000 - 0) / 1000 / 512) * 1000
print("S = %.5f ms   (promoted 97.89475)" % S)
Tms = (d * 1000) - (S / 512)
print("T = %.6f ms   (promoted 4.143569335937499)  %+.1f us" % (Tms, (Tms - 4.143569335937499) * 1000))

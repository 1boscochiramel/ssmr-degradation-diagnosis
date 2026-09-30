function dx = p7_nonneg(t, x, u, p)
% P7: emulate the NonNegative option that the upstream script requests (odeset 'NonNegative',
% 1:16*np) but Octave's ode15s ignores. Components at or below zero may not decrease further.
% SSMR_function is called exactly once, so the global F_H2 semantics are unchanged.
dx = SSMR_function(t, x, u, p);
idx = find(x <= 0);
dx(idx) = max(dx(idx), 0);
end

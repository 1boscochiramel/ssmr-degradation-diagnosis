function J = p6_jacfun(x, u, p, S, groups)
% P6v3: Jacobian function handed to ode15s; ode15s decides when to call it (as it would for its
% own finite differences). Preserves the global F_H2 so the recorded output is still the value
% from the last RHS call made by ode15s's integration, exactly as upstream.
global F_H2
saved = F_H2;
J = p6_jac(x(:), u, p, S, groups);
F_H2 = saved;
end

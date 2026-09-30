function J = p6_jac(x, u, p, S, groups)
% P6 amendment: coloured forward-difference Jacobian of the upstream SSMR_function at (x, u).
% Called before ode15s in each interval; its RHS calls never reach the recorded y_output.
n = numel(x);
f0 = SSMR_function(0, x, u, p);
I = []; K = []; V = [];
for g = 1:numel(groups)
  cols = groups{g};
  h = sqrt(eps)*max(abs(x(cols)), 1);
  xp = x; xp(cols) = xp(cols) + h;
  df = SSMR_function(0, xp, u, p) - f0;
  for c = 1:numel(cols)
    r = find(S(:, cols(c)));
    I = [I; r]; K = [K; cols(c)*ones(numel(r), 1)]; V = [V; df(r)/h(c)];
  end
end
J = sparse(I, K, V, n, n);
end

function [S, groups] = p6_pattern(Mode, np, P_in, T_in)
% P6 amendment: sparsity of d(RHS)/dx of the upstream SSMR_function, probed at the
% author-supplied ICFull and ICH2O states; greedy column colouring. Cached per mode/grid.
cache = sprintf('p6_pattern_mode%d_np%d.mat', Mode, np);
if exist(cache, 'file')
  c = load(cache); S = c.S ~= 0; groups = c.groups; return;
end
p = Parameters(P_in, T_in, np, 0, 0);
files = {sprintf('Mode%d_np%d.mat', Mode, np), sprintf('Mode%d_np%d_H2O.mat', Mode, np)};
n = 16*np; S = speye(n) ~= 0;
for f = files
  s = load(f{1}); x = s.x0c(:); u = s.u_ss;
  if u(1) == 0, u(1) = 0.0018; end   % probe with ethanol present so its terms appear
  f0 = SSMR_function(0, x, u, p);
  rows = []; cols = [];
  for j = 1:n
    xp = x; h = sqrt(eps)*max(abs(x(j)), 1); xp(j) = xp(j) + h;
    r = find(SSMR_function(0, xp, u, p) - f0 ~= 0);
    rows = [rows; r]; cols = [cols; j*ones(numel(r), 1)];
  end
  S = S | sparse(rows, cols, true, n, n);
end
% greedy colouring, densest columns first
[~, order] = sort(full(sum(S, 1)), 'descend');
groups = {}; used = {};
for j = order
  rj = find(S(:, j));
  placed = false;
  for g = 1:numel(groups)
    if ~any(used{g}(rj))
      groups{g}(end+1) = j; used{g}(rj) = true; placed = true; break;
    end
  end
  if ~placed
    groups{end+1} = j; u0 = false(n, 1); u0(rj) = true; used{end+1} = u0;
  end
end
S_store = struct('S', double(S), 'groups', {groups});   % sparse double: Octave 6.4 cannot reload sparse logical
save('-mat7-binary', cache, '-struct', 'S_store');
printf('P6 pattern: nnz %d, colours %d\n', nnz(S), numel(groups)); fflush(stdout);
end

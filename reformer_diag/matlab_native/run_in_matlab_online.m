% Reproduce the native MATLAB runs used for M1 equivalence (MATLAB Online R2026a, 2026-09-30).
% Fetches the pinned upstream commit, changes ONLY the README case settings in copies,
% runs each case in a clean PID state, and writes CSVs [time, y_output, u_output, y_sp].
% Note: control.m keeps PID state in persistent variables that SSMR_simulation.m's `clear`
% does not reset, so `clear control` is required between closed-loop cases.
W = fullfile(matlabdrive, 'ssmr_native');
if ~exist(W, 'dir'), mkdir(W); end
cd(W);
websave('up.zip', 'https://github.com/arcmateo/SSMR_Benchmark/archive/c6280844404cbef38da8a893a095a734bc0d4815.zip');
unzip('up.zip');
d = dir('SSMR_Benchmark-*'); q = fullfile(W, d(1).name, 'SSMR_simulator'); cd(q);
s0 = fileread('SSMR_simulation.m');
P = @(s,k,v) regexprep(s, ['(?m)^' k ' = [^;\r\n]*;'], [k ' = ' v ';'], 'once');
cases = {
  'CS1',  {'Mode','1'; 'Disturbance','0';   'Dist_time','1'; 'initial_conditions','0'; 't','30'; 'setpoint_profile','1'; 'simulation_type','1'}
  'CS2T', {'Mode','2'; 'Disturbance','1.1'; 'Dist_time','5'; 'initial_conditions','1'; 't','10'; 'setpoint_profile','0'; 'simulation_type','1'}
  'CS2P', {'Mode','2'; 'Disturbance','2.2'; 'Dist_time','5'; 'initial_conditions','1'; 't','10'; 'setpoint_profile','0'; 'simulation_type','1'}
  'STEP', {'Mode','1'; 'Disturbance','0';   'Dist_time','1'; 'initial_conditions','0'; 't','4';  'setpoint_profile','1'; 'simulation_type','0'}};
for i = 1:size(cases, 1)
  s = s0; kv = cases{i, 2};
  for j = 1:size(kv, 1), s = P(s, kv{j,1}, kv{j,2}); end
  if strcmp(cases{i,1}, 'STEP')   % input step at physical t = 2 min, before the open-loop ode15s call
    s = regexprep(s, '\[t,x\] = ode15s\(@\(t,x\)SSMR_function\(t,x,u,p\), \[0 t_s\], x0c, options\);', ...
        'if (k-1)*t_s >= 2 - 1e-9, u(1) = 0.0024; end; $0', 'once');
  end
  fid = fopen(['run_' cases{i,1} '.m'], 'w'); fwrite(fid, s); fclose(fid);
end
save(fullfile(W, 'cases.mat'), 'cases', 'q', 'W');
% Each script begins with `clear`, so run them one at a time from here:
clear control; run_CS1;  writematrix([time(:) y_output(:) u_output(:) y_sp(:)], fullfile(matlabdrive,'ssmr_native','CS1_np50_matlab_fresh.csv'));  close all
clear control; run_CS2T; writematrix([time(:) y_output(:) u_output(:) y_sp(:)], fullfile(matlabdrive,'ssmr_native','CS2T_np50_matlab_fresh.csv')); close all
clear control; run_CS2P; writematrix([time(:) y_output(:) u_output(:) y_sp(:)], fullfile(matlabdrive,'ssmr_native','CS2P_np50_matlab_fresh.csv')); close all
run_STEP;                writematrix([time(:) y_output(:) u_output(:) y_sp(:)], fullfile(matlabdrive,'ssmr_native','STEP_np50_matlab.csv'));       close all

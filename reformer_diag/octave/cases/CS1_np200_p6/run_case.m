%% BENCHMARK SIMULATOR
% Staged-separation membrane reactor (SSMR)
clear; close all; clc;
UP = getenv('SSMR_UPSTREAM'); addpath(UP, fullfile(UP,'ICFull'), fullfile(UP,'ICH2O'));

% Simulation setup ----------------------------------------------------

% Select the normal operating conditions: Mode 1, 2 or 3
% (See Table 2 in the paper)
Mode = 1;

% Select the disturbance scenario
% 0 = Without disturbances
% 1.1 = 10% step change in the inlet temperature
% 1.2 = -10% step change in the inlet temperature
% 2.1 = 20% step change in the inlet pressure
% 2.2 = -20% step change in the inlet pressure
% 3 = Catalyst deactivation
% 4 = Membrane fouling
Disturbance = 0; 

% Specify the time at which the disturbance is to be applied (if any)
Dist_time = 1; % [min]

% Select the initial conditions:
% (See more details in the supplementary material)
% 0 = steady state, reactor contains all compounds
% 1 = steady state, reactor contains only steam
initial_conditions = 0; 

% Select the overall simulation time
t = 30; % [min] - recommended: between 10 and 30 min

% Select the set-point profile
% (See Fig. 4 in the paper)
% 0 = constant set-point profile 
% 1 = set-point profile 1
% 2 = set-point profile 2
setpoint_profile = 1; 

% Select the simulation type:
% 0 = open-loop 
% 1 = closed-loop
simulation_type = 1;

% If you selected "control" in the options above, specify the control law to 
% be implemented
% 0 = PID (See Sections 5 and 6 in the paper)
% 1 = [...]
% 2 = [...]
% Here, users can implement their own control laws by adding a new number
% that corresponds to their control law defined in the control.m file
control_law = 0;






%% Please do not modify the lines below

% Number of points (spatial discretization): 50 or 200
np = 200;

% Sampling time
t_s = 0.1; % [min] - recommended: 0.1 min

switch Mode
   case 1
      P_in = 4.0; % [bar]
      T_in = 773.15; % [K]
      ss = 2.27354e-4; % [mol/min]
   case 2
      P_in = 6.0; % [bar]
      T_in = 823.15; % [K]
      ss = 2.76379e-4; % [mol/min]
   case 3
      P_in = 8.0; % [bar]
      T_in = 873.15; % [K]
      ss = 5.81357e-4; % [mol/min]
end

switch initial_conditions
    case 0 
        ss_filename = ['Mode',num2str(Mode),'_np',num2str(np),'.mat'];
    case 1 
        ss_filename = ['Mode',num2str(Mode),'_np',num2str(np),'_H2O','.mat'];
end
load(ss_filename); 
u = u_ss; 

time = 0:t_s:t;
y_output = zeros(size(time));
u_output = zeros(size(time));
y_sp = Profile(ss, time, t_s, setpoint_profile, Mode);

p = Parameters(P_in, T_in, np, 0, 0);

options = odeset('RelTol', 1e-4,'AbsTol', 1e-5,'MaxStep', 0.1,...
    'NonNegative', 1:8*2*np); % Options for the Solver
[P6S, P6G] = p6_pattern(Mode, np, P_in, T_in);  % P6

global F_H2

switch simulation_type
   case 0
      tic
      for k = 1:length(time)
            switch Disturbance
               case 0
                  p = Parameters(P_in, T_in, np, 0, 0);
               case 1.1
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in, T_in*1.1, np, k*t_s, d); % Load the parameters
                  end
               case 1.2
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in, T_in*0.9, np, k*t_s, d); % Load the parameters 
                  end
               case 2.1
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in*1.2, T_in, np, k*t_s, d); % Load the parameters
                  end
               case 2.2
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in*0.8, T_in, np, k*t_s, d); % Load the parameters
                  end
               case 3
                  d = 1;
                  p = Parameters(P_in, T_in, np, k*t_s, d); % Load the parameters
               case 4
                  d = 2;
                  p = Parameters(P_in, T_in, np, k*t_s, d); % Load the parameters
            end
          P6J = p6_jac(x0c(:), u, p, P6S, P6G);  % P6
          [t,x] = ode15s(@(t,x)SSMR_function(t,x,u,p), [0 t_s], x0c, odeset(options, 'Jacobian', P6J, 'Mass', speye(numel(x0c)), 'MStateDependence', 'none'));
          y_output(k) = F_H2;
          u_output(k) = u(1);
          x0c = x(end,:);
          fprintf('ROW %d %.17g %.17g %.17g %.1f\n', k, y_output(k), u_output(k), y_sp(k), toc); fflush(stdout);
      end
      toc
      out = [time(:), y_output(:), u_output(:), y_sp(:)];
      dlmwrite('trajectory.csv', out, 'precision', 17);
      save('-mat7-binary', 'final_state.mat', 'x0c', 'u');
      fprintf('SAVED trajectory.csv rows=%d\n', size(out,1)); fflush(stdout);
      return;  % P4: plotting skipped (headless); figures redrawn from CSV
      figure;
      subplot(2,1,1);
      plot(time, y_output, 'b', 'LineWidth', 2.0);
      set(gca,'FontSize', 16)
      hold on;
      xlabel('Time (min)', fontsize = 16); 
      ylabel('Pure H_{2} flow (mol/min)', fontsize = 16);
      title('System response', fontsize = 16);
      grid on  
      subplot(2,1,2);
      stairs(time, u_output, 'k', 'LineWidth', 2.0);
      set(gca,'FontSize', 16)
      xlabel('Time (min)', fontsize = 16); 
      ylabel('Inlet ethanol flow (mol/min)', fontsize = 16);
      ylim([0.0017, 0.0025]);
      title('Control input', fontsize = 16);
      grid on

   case 1

      tic
      for k = 1:length(time)
            switch Disturbance
               case 0
                  p = Parameters(P_in, T_in, np, 0, 0);
               case 1.1
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in, T_in*1.1, np, k*t_s, d); % Load the parameters
                  end
               case 1.2
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in, T_in*0.9, np, k*t_s, d); % Load the parameters 
                  end
               case 2.1
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in*1.2, T_in, np, k*t_s, d); % Load the parameters
                  end
               case 2.2
                  d = 0;
                  if k*t_s >= Dist_time + 0.2
                     p = Parameters(P_in*0.8, T_in, np, k*t_s, d); % Load the parameters
                  end
               case 3
                  d = 1;
                  p = Parameters(P_in, T_in, np, k*t_s, d); % Load the parameters
               case 4
                  d = 2;
                  p = Parameters(P_in, T_in, np, k*t_s, d); % Load the parameters
            end
          u_output(k) = u(1);
          P6J = p6_jac(x0c(:), u, p, P6S, P6G);  % P6
          [t,x] = ode15s(@(t,x)SSMR_function(t,x,u,p), [0 t_s], x0c, odeset(options, 'Jacobian', P6J, 'Mass', speye(numel(x0c)), 'MStateDependence', 'none'));
          y_output(k) = F_H2;
          u(1) = u(1) + control(control_law, t_s, y_output(k), y_sp(k));
          if u(1) <= 0.0018
             u(1) = 0.0018;
          end
          if u(1) >= 0.0024
             u(1) = 0.0024;
          end
          x0c = x(end,:);
          fprintf('ROW %d %.17g %.17g %.17g %.1f\n', k, y_output(k), u_output(k), y_sp(k), toc); fflush(stdout);
      end
      toc
      out = [time(:), y_output(:), u_output(:), y_sp(:)];
      dlmwrite('trajectory.csv', out, 'precision', 17);
      save('-mat7-binary', 'final_state.mat', 'x0c', 'u');
      fprintf('SAVED trajectory.csv rows=%d\n', size(out,1)); fflush(stdout);
      return;  % P4: plotting skipped (headless); figures redrawn from CSV
      figure;
      subplot(2,1,1);
      plot(time, y_output, 'b', 'LineWidth', 2.0);
      set(gca,'FontSize', 16)
      hold on;
      stairs(time, y_sp, 'r--', 'LineWidth', 2.0);
      xlabel('Time (min)',fontsize = 16); 
      ylabel('Pure H_{2} flow (mol/min)',fontsize = 16); 
      title('System response',fontsize = 16);
      legend('Pure H_{2} molar flow', 'Set-point',fontsize = 16);
      grid on  
      subplot(2,1,2);
      stairs(time, u_output, 'k', 'LineWidth', 2.0);
      set(gca,'FontSize', 16)
      xlabel('Time (min)',fontsize = 16);
      ylabel('Inlet ethanol flow (mol/min)',fontsize = 16);
      title('Control input',fontsize = 16);
      grid on
end
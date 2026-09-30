function run_m1_case(name)
% AI-generated cross-check draft for Bosco. Uses unmodified upstream functions.
% Run only in MATLAB/compatible Octave by the user; Codex has not executed it.
here = fileparts(mfilename('fullpath'));
upstream = fullfile(here,'..','..','upstream','SSMR_simulator');
addpath(upstream);
clear control;
global F_H2;
Mode=1; np=50; steam=false; duration=4; step_at=2; closed=false;
dist=0; kind=0;
switch name
    case 'STEP'
    case 'CS1'
        duration=30; step_at=Inf; closed=true; kind=1;
    case 'CS2T'
        Mode=2; duration=10; steam=true; closed=true; dist=1.1; step_at=Inf;
    case 'CS2P'
        Mode=2; duration=10; steam=true; closed=true; dist=2.2; step_at=Inf;
    case 'GRID50'
        duration=1; step_at=0.4;
    case 'GRID200'
        duration=1; step_at=0.4; np=200;
    case 'IC_DRIFT'
        duration=1; step_at=Inf;
    otherwise
        error('Unknown case');
end
if Mode==1
    P=4; T=773.15; ss=2.27354e-4;
else
    P=6; T=823.15; ss=2.76379e-4;
end
if steam
    path=fullfile(upstream,'ICH2O',sprintf('Mode%d_np%d_H2O.mat',Mode,np));
else
    path=fullfile(upstream,'ICFull',sprintf('Mode%d_np%d.mat',Mode,np));
end
ic=load(path); x=ic.x0c(:); u=ic.u_ss;
dt=0.1; count=round(duration/dt)+double(closed);
times=(0:count-1)*dt;
setpoints=Profile(ss,times,dt,kind,Mode);
opts=odeset('RelTol',1e-4,'AbsTol',1e-5,'MaxStep',0.1,'NonNegative',1:16*np);
p=Parameters(P,T,np,0,0); trace=zeros(count,10);
wall_start=tic;
for k=1:count
    t0=(k-1)*dt;
    if closed
        if k*dt>=5+0.2
            if dist==1.1, p=Parameters(P,T*1.1,np,0,0); end
            if dist==2.2, p=Parameters(P*0.8,T,np,0,0); end
        end
    elseif t0>=step_at-1e-12
        u(1)=0.0024;
    end
    used=u;
    [~,states]=ode15s(@(t,z)SSMR_function(t,z,used,p),[0 dt],x,opts);
    last=F_H2; x=states(end,:)';
    if ~isreal(states) || any(~isfinite(states(:)))
        error('Native integration produced complex or nonfinite states; no accepted trace claimed');
    end
    SSMR_function(dt,x,used,p); endpoint=F_H2;
    trace(k,:)=[t0,t0,t0+dt,last,endpoint,used(1),used(2),setpoints(k),x(4*np),x(end)];
    if closed
        u(1)=min(0.0024,max(0.0018,u(1)+control(0,dt,last,setpoints(k))));
    end
    fprintf('%s native interval %d/%d elapsed %.1fs\n',name,k,count,toc(wall_start));
end
folder=fullfile(here,'native_outputs'); if ~exist(folder,'dir'), mkdir(folder); end
file=fullfile(folder,[name '_trace.csv']);
if exist(file,'file'), error('Preserve existing native output; move it before a new run'); end
fid=fopen(file,'w');
fprintf(fid,'display_min,interval_start_min,physical_end_min,last_rhs_H2_mol_min,endpoint_H2_mol_min,ethanol_mol_min,water_mol_min,setpoint_H2_mol_min,reformer_outlet_H2_mol_m3,outlet_T_K\n');
fclose(fid); dlmwrite(file,trace,'-append','precision',17);
save(fullfile(folder,[name '_metadata.mat']),'name','Mode','np','path','opts');
runtime=version(); elapsed_seconds=toc(wall_start);
fid=fopen(fullfile(folder,[name '_runtime.json']),'w');
fprintf(fid,'{"runtime":"%s","elapsed_seconds":%.17g,"case":"%s","native":true}\n',runtime,elapsed_seconds,name);
fclose(fid);
fprintf('Saved %s; this is a native trace, not an automatic acceptance decision.\n',file);
end

%% ==============================
%% 批量处理：拆分 → 拼接 → 提取对应包络
%% 规则：谁先播放，就提取谁的包络
%% ==============================
clear; clc;

%% 路径设置
input_dir   = pwd;          
split_dir   = fullfile(pwd, 'split');   
output_dir  = fullfile(pwd, 'output'); 
env_dir     = fullfile(pwd, 'envelope'); % 包络保存文件夹

if ~exist(split_dir, 'dir'),  mkdir(split_dir);  end
if ~exist(output_dir, 'dir'), mkdir(output_dir); end
if ~exist(env_dir, 'dir'),    mkdir(env_dir);    end

%% 参数
segment_sec = 30;    
delay_sec   = 5;     
output_sec  = 30;
low_pass_cutoff = 15; % 包络低通截止频率（标准15Hz）

%% ==============================
%% 第一步：批量拆分声道
%% ==============================
for k = 1:16
    file = fullfile(input_dir, sprintf('%d.wav', k));
    if ~exist(file, 'file'), continue; end
    
    [y, fs] = audioread(file);
    if size(y,2) ~= 2, continue; end
    
    left  = y(:,1);
    right = y(:,2);
    
    audiowrite(fullfile(split_dir, sprintf('%d_left.wav', k)),  left,  fs);
    audiowrite(fullfile(split_dir, sprintf('%d_right.wav', k)), right, fs);
    fprintf('已拆分：%d.wav\n', k);
end

%% ==============================
%% 第二步：拼接 + 提取【对应包络】
%% ==============================
for k = 1:16
    lfile = fullfile(split_dir, sprintf('%d_left.wav', k));
    rfile = fullfile(split_dir, sprintf('%d_right.wav', k));
    
    if ~exist(lfile, 'file') || ~exist(rfile, 'file'), continue; end
    
    [left, fs]  = audioread(lfile);
    [right, fs] = audioread(rfile);
    
    seg_len = segment_sec * fs;
    N_left = floor(length(left) / seg_len);
    N_right = floor(length(right) / seg_len);
    n_pairs = min(N_left, N_right);
    
    if n_pairs < 1, continue; end
    
    delay_len = delay_sec * fs;
    output_len = output_sec * fs;

    % 设计包络提取低通滤波器
    [b, a] = butter(2, low_pass_cutoff/(fs/2), 'low');
    
    %% 开始处理每一段
    for i = 1:n_pairs
        L = left( (i-1)*seg_len + 1 : i*seg_len );
        R = right( (i-1)*seg_len + 1 : i*seg_len );
        
        if mod(i,2) == 1
            % ======================
            % 左先播放 → 提取【左】包络
            % ======================
            part1 = L(1:delay_len);
            part2 = L(delay_len+1:end) + R(1:end-delay_len);
            combined = [part1; part2];
            name = sprintf('%d_seg%02d_L_first', k, i);
            
            % 包络：左声道
            env = filtfilt(b, a, abs(L));  % 全波整流 + 15Hz 低通
            
        else
            % ======================
            % 右先播放 → 提取【右】包络
            % ======================
            part1 = R(1:delay_len);
            part2 = R(delay_len+1:end) + L(1:end-delay_len);
            combined = [part1; part2];
            name = sprintf('%d_seg%02d_R_first', k, i);
            
            % 包络：右声道
            env = filtfilt(b, a, abs(R));
        end
        
        % 保存音频
        combined = combined(1:output_len);
        audiowrite(fullfile(output_dir, [name,'.wav']), combined, fs);
        
        % 保存包络
        save(fullfile(env_dir, [name,'_envelope.mat']), 'env', 'fs');
        
        fprintf('已生成：%s.wav + 包络\n', name);
    end
end

disp('✅ 全部处理完成！');
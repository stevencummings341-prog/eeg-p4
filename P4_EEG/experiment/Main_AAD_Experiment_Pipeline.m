function Main_AAD_Experiment_Pipeline()
    % =========================================================
    % 0. 初始化与全局配置
    % =========================================================
    close all; clear; clc;
    
    % 弹出统一的启动界面，获取被试信息
    prompt = {'被试 ID (Subject ID):', 'EEG 串口号 (e.g. COM3):'};
    dlgTitle = 'AAD 听觉空间注意力主实验';
    defaultAnswer = {'Sub_01', 'COM3'};
    answer = inputdlg(prompt, dlgTitle, 1, defaultAnswer);
    if isempty(answer), return; end
    
    global_config.SubjectID = string(answer{1});
    global_config.PortName = string(answer{2});
    
    % 强力清理底层串口资源
    try delete(serialportfind); catch; end
    try delete(instrfindall); catch; end
    clear global Obj;
    
    % 初始化 PTB 窗口 (全局只打开一次)
    Screen('Preference', 'SkipSyncTests', 1);
    PsychDefaultSetup(2);
    InitializePsychSound(1);
    
    screens = Screen('Screens');
    screenNumber = max(screens);
    [window, windowRect] = PsychImaging('OpenWindow', screenNumber, [0 0 0]);
    [screenX, screenY] = Screen('WindowSize', window);
    Screen('BlendFunction', window, 'GL_SRC_ALPHA', 'GL_ONE_MINUS_SRC_ALPHA');
    KbName('UnifyKeyNames');
    
    % 初始化串口
    global Obj;
    if strcmpi(global_config.PortName, 'None')
        Obj = [];
    else
        Obj = serialport(char(global_config.PortName), 115200);
    end

    try
        % =========================================================
        % 1. 主实验开始
        % =========================================================
        showText(window, '听觉空间注意力 (AAD) 综合实验\n\n准备好后，按任意键开始', 50);
        
        % =========================================================
        % 2. Task 1: 空间方位辨别
        % =========================================================
        showText(window, '【实验一：空间听觉方位实验】\n\n即将开始，按任意键进入', 40);
        run_task1(window, global_config);
        showText(window, '实验一 已完成\n\n请闭眼休息 5 分钟', 40);
        take_rest(window, 300); % 300秒休息
        
        % =========================================================
        % 3. Task 2: 空间听觉图片实验
        % =========================================================
        showText(window, '【实验二：AAD 空间听觉图片实验】\n\n即将开始，按任意键进入', 40);
        run_task2(window, global_config);
        showText(window, '实验二 已完成\n\n请闭眼休息 5 分钟', 40);
        take_rest(window, 300);
        
        % =========================================================
        % 4. Task 3: AAD 竞争语音实验
        % =========================================================
        showText(window, '【实验三：AAD 竞争语音实验】\n\n即将开始，按任意键进入', 40);
        run_task3(window, global_config);
        
        % =========================================================
        % 5. 实验结束
        % =========================================================
        showText(window, '恭喜！所有实验任务已完成。\n\n感谢您的参与！', 50);
        WaitSecs(2);

    catch ME
        sca;
        rethrow(ME);
    end
    
    sca;
    PsychPortAudio('Close');
end

%% --- 辅助工具函数 ---

function showText(window, txt, textSize)
    Screen('TextSize', window, textSize);
    DrawFormattedText(window, double(char(txt)), 'center', 'center', [1 1 1]);
    Screen('Flip', window);
    KbStrokeWait(-1);
    Screen('Flip', window);
    WaitSecs(0.5);
end

function take_rest(window, duration)
    startTime = GetSecs();
    while GetSecs() - startTime < duration
        remaining = round(duration - (GetSecs() - startTime));
        txt = sprintf('休息中...\n\n剩余时间: %d 秒\n\n(完成后按空格键跳过)', remaining);
        Screen('TextSize', window, 40);
        DrawFormattedText(window, double(char(txt)), 'center', 'center', [1 1 1]);
        Screen('Flip', window);
        
        [keyIsDown, ~, keyCode] = KbCheck;
        if keyIsDown && keyCode(KbName('space')), break; end
        WaitSecs(0.1);
    end
end

%% --- Task 封装逻辑  ---
%% Task 1 function
function run_task1(window, global_config)
    % =========================================================
    % 1. 参数与路径配置 (基于 Task 1 原始逻辑)
    % =========================================================
    angles = [0, 45, 90, 135, 180, 225, 270, 315];
    nTotalTrials = 32; 
    basePath = "D:\EEG_P2\Task 1\Trials"; % 请确保此路径存在
    
    % 构建音频路径映射
    audioMap = strings(1, length(angles));
    for a = 1:length(angles)
        audioMap(a) = fullfile(basePath, sprintf("stimulus_az%d_pulsed.wav", angles(a)));
    end
    
    % 生成随机序列：确保相邻两次音频角度不同
    trialAngleIndices = zeros(1, nTotalTrials);
    for t = 1:nTotalTrials
        if t == 1
            trialAngleIndices(t) = randi(length(angles));
        else
            nextIdx = randi(length(angles));
            while nextIdx == trialAngleIndices(t-1)
                nextIdx = randi(length(angles));
            end
            trialAngleIndices(t) = nextIdx;
        end
    end

    % =========================================================
    % 2. 硬件与音频初始化 (仅初始化音频，window由主程序提供)
    % =========================================================
    % 检查 global Obj 是否在主程序已创建 (send_trigger 会用到)
    fs = 44100;
    pahandle = PsychPortAudio('Open', [], 1, 1, fs, 2);
    
    % =========================================================
    % 3. 实验指导语
    % =========================================================
    WelcomeText = '【实验一：空间听觉方位实验】\n\n请在听到声音后，判断声音传来的方位。\n\n(按任意键开始)';
    Screen('TextSize', window, 40);
    DrawFormattedText(window, double(char(WelcomeText)), 'center', 'center', [1 1 1]);
    Screen('Flip', window); 
    KbStrokeWait(-1); % 等待任意按键
    
    expResults = struct();
    expResults.Config = global_config;
    correct_count = 0;

    % =========================================================
    % 4. 试次主循环
    % =========================================================
    % 如果 global_config 包含 StartTrial 则使用，否则从 1 开始
    startT = 1;
    if isfield(global_config, 'StartTrial'), startT = global_config.StartTrial; end

    for i = startT : nTotalTrials
        targetIdx = trialAngleIndices(i);
        targetAngle = angles(targetIdx);
        audioFile = char(audioMap(targetIdx));
        
        % 加载音频
        [audioData, ~] = audioread(audioFile);
        if size(audioData,2) == 1, audioData = repmat(audioData, 1, 2); end
        PsychPortAudio('FillBuffer', pahandle, audioData');
        
        % 准备阶段：注视点
        Screen('TextSize', window, 60);
        DrawFormattedText(window, '+', 'center', 'center', [1 1 1]);
        Screen('Flip', window);
        WaitSecs(0.8);
        
        % 播放音频并发送 Trigger (Trigger 值为 1)
        PsychPortAudio('Start', pahandle, 1, 0, 1);
        expResults.TrialData(i).AudioStartTime = GetSecs();
        send_trigger(1); 
        WaitSecs(0.05);
        send_trigger(0);
        
        % 等待音频播放结束
        audioLen = length(audioData) / fs;
        WaitSecs(audioLen);
        PsychPortAudio('Stop', pahandle);
        Screen('Flip', window);
        WaitSecs(0.3);
        
        % 采集反应：方位选择
        QuestionText = '请选择声源方位:\n\n1:0°  2:45°  3:90°  4:135°\n5:180°  6:225°  7:270°  8:315°'; %待修改
        
        Screen('TextSize', window, 35);
        DrawFormattedText(window, double(char(QuestionText)), 'center', 'center', [1 1 1]);
        Screen('Flip', window);
        
        t_start = GetSecs();
        resp_made = false;
        while ~resp_made
            [keyIsDown, ~, keyCode] = KbCheck(-1);
            if keyIsDown
                keys = KbName(keyCode);
                % 兼容部分电脑键盘识别结果可能为 '1!' 等情况
                if ischar(keys) && any(strcmp(keys(1), {'1','2','3','4','5','6','7','8'}))
                    resp_idx = str2double(keys(1)); 
                    resp_angle = angles(resp_idx);
                    resp_made = true;
                elseif keyCode(KbName('escape'))
                    error('实验被手动强行退出 (ESC)');
                end
            end
            WaitSecs(0.005);
        end
        
        % 记录行为数据
        expResults.TrialData(i).TrialNum = i;
        expResults.TrialData(i).TargetAngle = targetAngle;
        expResults.TrialData(i).ResponseAngle = resp_angle;
        expResults.TrialData(i).RT = GetSecs() - t_start;
        expResults.TrialData(i).IsCorrect = (targetAngle == resp_angle);
        
        if expResults.TrialData(i).IsCorrect, correct_count = correct_count + 1; end
        
        % 试次间休息
        if i < nTotalTrials
            DrawFormattedText(window, '准备好后，按【空格键】开始下一试次', 'center', 'center', [1 1 1]);
            Screen('Flip', window);
            while true
                [kd, ~, kc] = KbCheck(-1);
                if kd && kc(KbName('space')), break; end
                WaitSecs(0.01);
            end
        end
    end

    % =========================================================
    % 5. 保存数据与清理音频 (严禁在此处 sca)
    % =========================================================
    expResults.Accuracy = correct_count / nTotalTrials;
    
    dataFolder = 'Spatial_EEG_Data';
    if ~exist(dataFolder, 'dir'), mkdir(dataFolder); end
    saveName = fullfile(dataFolder, sprintf('Spatial_%s_%s.mat', global_config.SubjectID, datestr(now, 'yyyymmdd_HHMMSS')));
    save(saveName, 'expResults');
    
    % 清理当前任务的音频句柄
    PsychPortAudio('Close', pahandle);
    
    % 告知主程序：任务 1 已结束
    disp('Task 1 completed and data saved.');
end

%% Task 2 function
function run_task2(window, global_config)
    % =========================================================
    % 1. 参数与路径配置 (基于 Task 2 原始逻辑)
    % =========================================================
    % 使用主实验传入的配置，并设定任务特有的参数
    config = struct();
    config.SubjectID = global_config.SubjectID;
    config.nTrials = 32; % 也可以根据需要从 global_config 传入
    config.BaseDir = 'D:\EEG_P2\Task 2\Batch_Trials'; % 确保此路径存在
    
    % --- 音频初始化 ---
    fs = 44100;
    pahandle = PsychPortAudio('Open', [], 1, 1, fs, 2);
    
    % --- 按键定义 ---
    KbName('UnifyKeyNames');
    up_key = KbName('UpArrow'); down_key = KbName('DownArrow');
    left_key = KbName('LeftArrow'); right_key = KbName('RightArrow');
    esc_key = KbName('escape'); space_key = KbName('space');
    
    % --- 获取屏幕中心点用于布局 ---
    [screenXpixels, screenYpixels] = Screen('WindowSize', window);

    % =========================================================
    % 2. 指导语呈现
    % =========================================================
    WelcomeText = '【实验二：AAD 空间听觉图片实验】\n\n请听音频，并在随后出现的四张图中选出正确的图片。\n\n(按任意键开始)';
    InstructionText = '请使用【方向键】选择对应的图片位置：\n↑(左上)  →(右上)  ←(左下)  ↓(右下)\n\n(按任意键继续)';
    
    Screen('TextSize', window, 40);
    DrawFormattedText(window, double(char(WelcomeText)), 'center', 'center', [1 1 1]);
    Screen('Flip', window); 
    KbStrokeWait(-1);
    
    DrawFormattedText(window, double(char(InstructionText)), 'center', 'center', [1 1 1]);
    Screen('Flip', window);
    KbStrokeWait(-1);

    expResults = struct();
    expResults.Config = config;
    correct_count = 0;

    % =========================================================
    % 3. 试次主循环
    % =========================================================
    for i = 1 : config.nTrials
        % --- 路径构建 ---
        trial_str = sprintf('Trial_%02d', i);
        current_trial_dir = fullfile(config.BaseDir, trial_str);
        audio_path = fullfile(current_trial_dir, ['audio_', trial_str, '.wav']);
        img_names = {'option_correct.png', 'option_distractor_1.png', 'option_distractor_2.png', 'option_distractor_3.png'};
        
        % --- 加载图片并打乱位置 (建立纹理) ---
        texs = [];
        shuffled_idx = randperm(4); 
        correct_pos = find(shuffled_idx == 1); 
        
        for k = 1:4
            img_full_path = fullfile(current_trial_dir, img_names{shuffled_idx(k)});
            if exist(img_full_path, 'file')
                img_data = imread(img_full_path);
                texs(k) = Screen('MakeTexture', window, img_data);
            end
        end

        % --- 加载音频 ---
        [audioData, ~] = audioread(audio_path);
        if size(audioData,2) == 1, audioData = repmat(audioData, 1, 2); end
        PsychPortAudio('FillBuffer', pahandle, audioData');

        % --- 播放与打标 (Trigger 2) ---
        Screen('TextSize', window, 60);
        DrawFormattedText(window, '+', 'center', 'center', [1 1 1]);
        Screen('Flip', window);
        
        PsychPortAudio('Start', pahandle, 1, 0, 1);
        send_trigger(2); 
        WaitSecs(0.05);
        send_trigger(0);
        
        % 等待音频结束
        WaitSecs(length(audioData)/fs);
        Screen('Flip', window);
        WaitSecs(0.5);

        % --- 呈现图片选择界面 (田字格布局) ---
        sqSize = 300; gap = 100;
        rects(:,1) = CenterRectOnPoint([0 0 sqSize sqSize], screenXpixels/2-gap-sqSize/2, screenYpixels/2-gap-sqSize/2); % 左上
        rects(:,2) = CenterRectOnPoint([0 0 sqSize sqSize], screenXpixels/2+gap+sqSize/2, screenYpixels/2-gap-sqSize/2); % 右上
        rects(:,3) = CenterRectOnPoint([0 0 sqSize sqSize], screenXpixels/2-gap-sqSize/2, screenYpixels/2+gap+sqSize/2); % 左下
        rects(:,4) = CenterRectOnPoint([0 0 sqSize sqSize], screenXpixels/2+gap+sqSize/2, screenYpixels/2+gap+sqSize/2); % 右下
        
        for k = 1:4
            Screen('DrawTexture', window, texs(k), [], rects(:,k));
        end
        Screen('TextSize', window, 30);
        DrawFormattedText(window, '请使用方向键选择 (↑/→/←/↓)', 'center', screenYpixels - 100, [1 1 1]);
        Screen('Flip', window);

        % --- 获取响应 ---
        t_start = GetSecs();
        resp_pos = 0;
        while true
            [keyIsDown, ~, keyCode] = KbCheck(-1);
            if keyIsDown
                if keyCode(esc_key), error('用户强行退出实验 (ESC)');
                elseif keyCode(up_key),    resp_pos = 1; % 左上
                elseif keyCode(right_key), resp_pos = 2; % 右上
                elseif keyCode(left_key),  resp_pos = 3; % 左下
                elseif keyCode(down_key),  resp_pos = 4; % 右下
                end
                if resp_pos > 0, break; end
            end
            WaitSecs(0.005);
        end
        rt = GetSecs() - t_start;

        % --- 判定与记录 ---
        isCorrect = (resp_pos == correct_pos);
        if isCorrect, correct_count = correct_count + 1; end
        expResults.TrialData(i).TrialNum = i;
        expResults.TrialData(i).RT = rt;
        expResults.TrialData(i).IsCorrect = isCorrect;
        expResults.TrialData(i).CorrectPosition = correct_pos;
        expResults.TrialData(i).ResponsePosition = resp_pos;

        % 释放纹理资源
        Screen('Close', texs);
        
        % 休息提示 (每8个Trial休息一次)
        if mod(i, 8) == 0 && i < config.nTrials
            DrawFormattedText(window, '您可以稍作休息\n\n准备好后请按【空格键】继续', 'center', 'center', [1 1 1]);
            Screen('Flip', window);
            while true
                [~,~,keyCode] = KbCheck(-1);
                if keyCode(space_key), break; end
                WaitSecs(0.01);
            end
        end
    end

    % =========================================================
    % 4. 数据保存与清理 (不执行 sca)
    % =========================================================
    expResults.Accuracy = correct_count / config.nTrials;
    saveDir = 'Results_Task2';
    if ~exist(saveDir, 'dir'), mkdir(saveDir); end
    saveName = fullfile(saveDir, sprintf('Task2_%s_%s.mat', config.SubjectID, datestr(now, 'yyyymmdd_HHMM')));
    save(saveName, 'expResults');

    PsychPortAudio('Close', pahandle);
    disp('Task 2 已完成并保存数据。');
end


%% Task 3 function
function run_task3(window, config)
    % --- 1. task 3路径与题库加载 ---
    baseAudioPath = 'E:\Dataset_Audio_EEG\My_data\output'; % 音频存放路径
    load("QuestionsDB.mat"); % 必须确保此文件在路径下
    
    % --- 2. 获取播放列表 ---
    [seqFile, seqPath] = uigetfile('*.txt', '请选择本轮实验的音频播放列表 (.txt 格式)');
    if isequal(seqFile, 0), return; end
    
    % 读取并解析列表
    fid = fopen(fullfile(seqPath, seqFile), 'r', 'n', 'UTF-8');
    rawLines = textscan(fid, '%s', 'Delimiter', '\n');
    fclose(fid);
    probe = string(rawLines{1});
    probe = probe(strlength(probe) > 0);
    nTrials = length(probe);
    
    % 随机化顺序
    randIndex = randperm(nTrials);
    probe = probe(randIndex);

    % --- 3. 音频句柄初始化 ---
    % 注意：window 已由主程序传入，只需初始化音频
    fs = 44100;
    pahandle = PsychPortAudio('Open', [], 1, 1, fs, 2);
    
    % 键位定义
    KbName('UnifyKeyNames');
    esc_key = KbName('escape'); T_key = KbName('T'); F_key = KbName('F'); space_key = KbName('space');
    disp('Task 3 Running...');

    expResults = struct();
    expResults.Config = global_config;
    correct_count = 0;
    total_questions_asked = 0;

    for i = 1 : nTrials  % 默认从1开始，或使用 global_config.StartTrial
        % --- 提取 Trial ID 与 条件 ---
        filepath = char(probe(i));
        % 正则匹配 trial_id 的逻辑 ...
        name = regexp(filepath, '([^\\]+)\.wav$', 'tokens');
        trial_id = name{1}{1};
        expResults.TrialData(i).TrialNum = i;
        expResults.TrialData(i).TrialID = trial_id;
        expResults.TrialData(i).AudioPath = filepath;

        if contains(filepath, '_L_')
            expResults.TrialData(i).Condition = 'Left';
        elseif contains(filepath, '_R_')
            expResults.TrialData(i).Condition = 'Right';
        else
            expResults.TrialData(i).Condition = 'Unknown';
        end

        % --- 获取对应题目 ---
        idx = strcmp(all_ids, trial_id);
        segment = questionData(idx);
      
        % 题目随机化提取逻辑
        qOrder = randperm(2);

        first_q_struct = segment.questions(qOrder(1));
        second_q_struct = segment.questions(qOrder(2));

        q1_raw = first_q_struct.q;
        if iscell(q1_raw), q1_raw = q1_raw{1}; end
        if isstring(q1_raw), q1_raw = char(q1_raw); end
        try q1_ans = first_q_struct.ans; catch; q1_ans = 'Unknown'; end

        q2_raw = second_q_struct.q;
        if iscell(q2_raw), q2_raw = q2_raw{1}; end
        if isstring(q2_raw), q2_raw = char(q2_raw); end
        try q2_ans = second_q_struct.ans; catch; q2_ans = 'Unknown'; end

        expResults.TrialData(i).QuestionOrder = qOrder;


        % --- 音频处理 (难度调整) ---
        [audioData, fs_audio] = audioread(filepath);
        % 
        % 根据难度设定计算干扰源乘数
        nonTargetMultiplier = max(0, 1.0 - config.Difficulty);

        if strcmp(expResults.TrialData(i).Condition, 'Left')
            audioData(:, 2) = audioData(:, 2) * nonTargetMultiplier;
        elseif strcmp(expResults.TrialData(i).Condition, 'Right')
            audioData(:, 1) = audioData(:, 1) * nonTargetMultiplier;
        end

        audioData(audioData > 1.0) = 1.0;
        audioData(audioData < -1.0) = -1.0;

        % 真实倍速处理：对音频矩阵进行降采样提取
        if config.SpeedMultiplier > 1
            speedStep = round(config.SpeedMultiplier);
            audioData = audioData(1:speedStep:end, :);
        end

        
        % --- 播放与打标 ---
        PsychPortAudio('FillBuffer', pahandle, audioData');
        % 呈现注视点
        Screen('TextSize', window, 100);
        DrawFormattedText(window, '+', 'center', 'center', [1 1 1]);
        Screen('Flip', window);
        
        PsychPortAudio('Start', pahandle, 1, 0, 1);
        send_trigger(3); % 发送 Task 3 的起始 Trigger
        WaitSecs(0.05);
        send_trigger(0);

        % 根据重采样后的物理长度计算真实的等待时间
        waitTime = length(audioData) / fs_audio;
        if waitTime > 0.05
            WaitSecs(waitTime - 0.05); 
        end

        Screen('Flip', window); WaitSecs(0.3);

        Screen('TextSize', window, 50);
        DrawFormattedText(window, double(char(InstructionText2)), 'center', 'center', [1 1 1]);
        Screen('Flip', window); KbStrokeWait(-1);

        
        % --- 答题逻辑 (T/F 判定) ---
        % 依次呈现 Q1 和 Q2，捕获 T_key 或 F_key
        % ... (直接插入原代码中的两个 while 循环) ...
        Screen('TextSize', window, 70);
        DrawFormattedText(window, double(q1_raw), 'center', 'center', [1 1 1]);
        Screen('Flip', window);

        t_q1_start = GetSecs();
        while true
            [keyIsDown, ~, keyCode] = KbCheck(-1); % 强制监听所有键盘
            if keyIsDown
                if any(keyCode(esc_key))
                    error('>>> 实验被用户终止 (ESC) <<<');
                elseif any(keyCode(T_key))
                    resp = 'T'; resp_val = 1; break;
                elseif any(keyCode(F_key))
                    resp = 'F'; resp_val = 0; break;
                end
            end
            WaitSecs(0.005); % 极短休眠防 CPU 卡死
        end
        expResults.TrialData(i).PresentedQ1_RT = GetSecs() - t_q1_start;
        expResults.TrialData(i).PresentedQ1_Resp = resp;
        expResults.TrialData(i).PresentedQ1_Correct = strcmp(resp, q1_ans);
        if strcmp(resp, q1_ans), correct_count = correct_count + 1; end
        total_questions_asked = total_questions_asked + 1;

        Screen('Flip', window); WaitSecs(0.2);

        % ---------------- 呈现第二题 ----------------
        Screen('TextSize', window, 70);
        DrawFormattedText(window, double(q2_raw), 'center', 'center', [1 1 1]);
        Screen('Flip', window);

        t_q2_start = GetSecs();
        while true
            [keyIsDown, ~, keyCode] = KbCheck(-1);
            if keyIsDown
                if any(keyCode(esc_key))
                    error('>>> 实验被用户终止 (ESC) <<<');
                elseif any(keyCode(T_key))
                    resp = 'T'; resp_val = 1; break;
                elseif any(keyCode(F_key))
                    resp = 'F'; resp_val = 0; break;
                end
            end
            WaitSecs(0.005);
        end
        expResults.TrialData(i).PresentedQ2_RT = GetSecs() - t_q2_start;
        expResults.TrialData(i).PresentedQ2_Resp = resp;
        expResults.TrialData(i).PresentedQ2_Correct = strcmp(resp, q2_ans);
        if strcmp(resp, q2_ans), correct_count = correct_count + 1; end
        total_questions_asked = total_questions_asked + 1;
        
        % --- 休息控制 ---
        if mod(i, 4) == 0 && i < nTrials
             % 插入原代码中的 RestText 提示逻辑
        end
    end


    % --- 保存数据 ---
    expResults.OverallAccuracy = correct_count / total_questions_asked;
    dataFolder = 'sub_Data';
    if ~exist(dataFolder, 'dir'), mkdir(dataFolder); end
    saveName = fullfile(dataFolder, sprintf('AAD_Task3_%s_%s.mat', global_config.SubjectID, datestr(now, 'yyyymmdd_HHMMSS')));
    save(saveName, 'expResults');

    % --- 清理音频 ---
    PsychPortAudio('Close', pahandle);
    % 注意：不要在这里写 sca;
    disp('Task 3 completed and data saved.');
end
%% Trigger function
% 统一 Trigger 函数
function send_trigger(trigger)
    global Obj
    if isempty(Obj) || ~isvalid(Obj), return; end
    hex_trigger = dec2hex(trigger);
    if trigger < 16, hex_trigger = ['0', hex_trigger]; end
    trig_bytes = hex2dec([hex_trigger; '55'; '66'; '0D']);
    write(Obj, trig_bytes, "uint8");
end
% Clear the workspace and the screen
try
    close all;
    clear;

    % =========================================================
    % 0. 强力清理底层资源
    % =========================================================
    try delete(serialportfind); catch; end
    try delete(instrfindall); catch; end
    clear global Obj;

    % =========================================================
    % 1. 实验基础路径与图形化启动界面
    % =========================================================
    % 设定音频文件的基础存放路径 (播放列表 txt 中仅需包含纯文件名)
    baseAudioPath = 'E:\Dataset_Audio_EEG\My_data\output';

    prompt = {
        '1. 被试 ID (Subject ID):', ...
        '2. 起始试次 (Start Trial，默认从 1 开始):', ...
        '3. 脑电 Trigger 串口号 (填 None 则进入无硬件测试):', ...
        '4. 音频倍速模式 (1=正常, 50=飞速测试):', ...
        '5. 难度设置 (0=正常, 0.5=简单(干扰减半), -0.5=困难(干扰增强)):'
        };
    dlgTitle = 'AAD 实验启动配置';
    numLines = 1;
    defaultAnswer = {'Sub_01', '1', 'COM3', '1', '0'};
    answer = inputdlg(prompt, dlgTitle, numLines, defaultAnswer);

    if isempty(answer)
        error('>>> 实验被主试取消（未完成参数配置）。');
    end

    config = struct();
    config.SubjectID = string(answer{1});
    config.StartTrial = str2double(answer{2});
    config.PortName = string(answer{3});
    config.SpeedMultiplier = str2double(answer{4});
    config.Difficulty = str2double(answer{5});
    config.ExpDate = datestr(now, 'yyyy-mm-dd HH:MM:SS');

    % =========================================================
    % 2. 动态选择音频播放列表 (Sequence File)
    % =========================================================
    [seqFile, seqPath] = uigetfile('*.txt', '请选择本轮实验的音频播放列表 (.txt 格式)');
    if isequal(seqFile, 0)
        error('>>> 实验被主试取消（未选择音频列表）。');
    end

    config.SequenceFile = fullfile(seqPath, seqFile);

    % 从 txt 文件中读取纯文件名列表
    fid = fopen(config.SequenceFile, 'r', 'n', 'UTF-8');
    if fid == -1, error('无法打开选择的列表文件'); end
    rawLines = textscan(fid, '%s', 'Delimiter', '\n');
    fclose(fid);

    % 过滤空行并转换为标准数组
    probe = string(rawLines{1});
    probe = probe(strlength(probe) > 0);

    nTrials = length(probe);
    if nTrials == 0
        error('>>> 选择的列表中没有读取到任何有效音频文件名！');
    end

    fprintf('\n=====================================\n');
    fprintf('实验配置就绪:\n');
    fprintf('被试: %s | 起始试次: %d | 倍速: %dx\n', config.SubjectID, config.StartTrial, config.SpeedMultiplier);
    fprintf('串口: %s | 难度设定: %.2f\n', config.PortName, config.Difficulty);
    fprintf('播放列表: %s (共包含 %d 个音频)\n', seqFile, nTrials);
    fprintf('音频目录: %s\n', baseAudioPath);
    fprintf('=====================================\n\n');

    % 打乱 Trial 顺序
    randIndex = randperm(nTrials);
    probe = probe(randIndex);

    % =========================================================
    % 3. 硬件与 PTB 初始化
    % =========================================================
    Screen('Preference','SkipSyncTests', 1);
    global Obj;

    if strcmpi(config.PortName, 'None')
        disp('⚠️ 当前为【无硬件模式】，跳过串口初始化，不会发送 Trigger。');
        Obj = [];
    else
        disp(['正在连接脑电 Trigger 接口 ', char(config.PortName), ' ...']);
        Obj = serialport(char(config.PortName), 115200, 'parity', 'none', 'databits', 8, 'stopbits', 1);
        try fopen(Obj); catch; end
        disp('>>> 接口连接成功！');
    end

    PsychDefaultSetup(2);
    InitializePsychSound(1);
    screens = Screen('Screens');
    fs = 44100;
    pahandle = PsychPortAudio('Open', [], 1, 1, fs, 2);

    screenNumber = max(screens);
    black = BlackIndex(screenNumber);
    [window, windowRect] = PsychImaging('OpenWindow', screenNumber, black);
    Screen('BlendFunction', window, 'GL_SRC_ALPHA', 'GL_ONE_MINUS_SRC_ALPHA');
    ifi = Screen('GetFlipInterval', window);

    try Screen('TextFont', window, 'SimHei'); catch; Screen('TextFont', window, '黑体'); end
    
    % ---------------- 新增：对齐第一份代码的队列按键逻辑 ----------------
    KbName('UnifyKeyNames');
    esc_key = KbName('escape'); T_key = KbName('T'); F_key = KbName('F'); space_key = KbName('space');

    keysOfInterest = zeros(1, 256);
    keysOfInterest([esc_key, T_key, F_key, space_key]) = 1;
    KbQueueCreate([], keysOfInterest);
    KbQueueStart([]);
    ListenChar(2); % 拦截键盘输入，防止漏键和敲入代码窗口

    % =========================================================
    % 4. 数据与题库准备
    % =========================================================
    load("QuestionsDB.mat");

    expResults = struct();
    expResults.Config = config;
    expResults.TrialData = struct();
    correct_count = 0;
    total_questions_asked = 0; 

    % 指导语优化：明确按键目标，剔除 KbStrokeWait 的不可控性
    WelcomeText = '欢迎参加听觉实验\n\n(按 空格键 继续)';
    EndText = '实验结束。感谢您的参与！\n\n(按 空格键 退出)';
    InstructionText1 = ['您将听到一段包含两个说话人的音频。\n\n请【仅关注】首先开始说话的那个声音。\n\n(按 空格键 继续)\n' ];
    InstructionText2 = ['接下来请回答两个判断题。\n\n正确按 T 键，错误按 F 键。\n\n按 空格键 开始答题。'];
    RestText = '您可以稍作休息。\n\n准备好后，请按 空格键 继续。';

    % 开始界面
    Screen('TextSize', window, 50);
    DrawFormattedText(window, double(char(WelcomeText)), 'center', 'center', [1 1 1]);
    Screen('Flip', window); 
    wait_for_key(space_key, esc_key);

    DrawFormattedText(window, double(char('按 空格键 正式开始实验！')), 'center', 'center', [1 1 1]);
    Screen('Flip', window); 
    wait_for_key(space_key, esc_key);

    % =========================================================
    % 5. 试次主循环 (Trial Loop)
    % =========================================================
    for i = config.StartTrial : nTrials

        filepath = char(probe(i));
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

        idx = strcmp(all_ids, trial_id);
        segment = questionData(idx);

        % =========================================================
        % 问题顺序随机化核心逻辑
        % =========================================================
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

        % =========================================================
        % 音频加载、难度调整与倍速重采样
        % =========================================================
        [audioData, fs_audio] = audioread(filepath);
        audioData = double(audioData);
        if size(audioData,2) == 1, audioData = repmat(audioData, 1, 2); end

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

        % 缓冲已处理好的音频
        PsychPortAudio('FillBuffer', pahandle, audioData');

        Screen('TextSize', window, 50);
        DrawFormattedText(window, double(char(InstructionText1)), 'center', 'center', [1 1 1]);
        Screen('Flip', window); 
        wait_for_key(space_key, esc_key);

        Screen('TextSize', window, 100);
        for frame = 1:round(0.3/ifi)
            DrawFormattedText(window, '+', 'center', 'center', [1 1 1]);
            Screen('Flip', window);
        end

        % =========================================================
        % 音频播放与打标 (时长自适应)
        % =========================================================
        PsychPortAudio('Start', pahandle, 1, 0, 1);
        expResults.TrialData(i).AudioStartTime = GetSecs();
        send_trigger(1);
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
        Screen('Flip', window); 
        wait_for_key(space_key, esc_key);

        % ---------------- 呈现第一题 ----------------
        Screen('TextSize', window, 70);
        DrawFormattedText(window, double(q1_raw), 'center', 'center', [1 1 1]);
        Screen('Flip', window);

        KbQueueFlush([]);
        t_q1_start = GetSecs();
        while true
            [pressed, firstPress] = KbQueueCheck([]);
            if pressed
                if firstPress(esc_key) > 0
                    error('>>> 实验被用户终止 (ESC) <<<');
                elseif firstPress(T_key) > 0
                    resp = 'T'; resp_val = 1; rt = firstPress(T_key) - t_q1_start; break;
                elseif firstPress(F_key) > 0
                    resp = 'F'; resp_val = 0; rt = firstPress(F_key) - t_q1_start; break;
                end
            end
            WaitSecs(0.005);
        end
        expResults.TrialData(i).PresentedQ1_RT = rt;
        expResults.TrialData(i).PresentedQ1_Resp = resp;
        expResults.TrialData(i).PresentedQ1_Correct = strcmp(resp, q1_ans);
        if strcmp(resp, q1_ans), correct_count = correct_count + 1; end
        total_questions_asked = total_questions_asked + 1;

        Screen('Flip', window); WaitSecs(0.2);

        % ---------------- 呈现第二题 ----------------
        Screen('TextSize', window, 70);
        DrawFormattedText(window, double(q2_raw), 'center', 'center', [1 1 1]);
        Screen('Flip', window);

        KbQueueFlush([]);
        t_q2_start = GetSecs();
        while true
            [pressed, firstPress] = KbQueueCheck([]);
            if pressed
                if firstPress(esc_key) > 0
                    error('>>> 实验被用户终止 (ESC) <<<');
                elseif firstPress(T_key) > 0
                    resp = 'T'; resp_val = 1; rt = firstPress(T_key) - t_q2_start; break;
                elseif firstPress(F_key) > 0
                    resp = 'F'; resp_val = 0; rt = firstPress(F_key) - t_q2_start; break;
                end
            end
            WaitSecs(0.005);
        end
        expResults.TrialData(i).PresentedQ2_RT = rt;
        expResults.TrialData(i).PresentedQ2_Resp = resp;
        expResults.TrialData(i).PresentedQ2_Correct = strcmp(resp, q2_ans);
        if strcmp(resp, q2_ans), correct_count = correct_count + 1; end
        total_questions_asked = total_questions_asked + 1;

        % 节律控制 (对齐队列监听方式)
        if i < nTrials
            Screen('TextSize', window, 50);
            msg = double(char('按 空格键 进入下一个 Trial。'));
            if mod(i, 4) == 0, msg = double(char(RestText)); end
            DrawFormattedText(window, msg, 'center', 'center', [1 1 1]);
            Screen('Flip', window);
            
            wait_for_key(space_key, esc_key);
        end
        Screen('Flip', window); WaitSecs(0.3);
    end

    % =========================================================
    % 6. 数据保存与安全退出
    % =========================================================
    expResults.OverallAccuracy = correct_count / total_questions_asked;
    fprintf('\n>>> 实验结束。本轮答题准确率: %.2f%%\n', expResults.OverallAccuracy * 100);

    dataFolder = 'sub_Data'; 

    if ~exist(dataFolder, 'dir')
        mkdir(dataFolder);
    end

    currentTime = datestr(now, 'yyyymmdd_HHMMSS');
    fileName = sprintf('AAD_Data_%s_%s.mat', config.SubjectID, currentTime);
    fullSavePath = fullfile(dataFolder, fileName);

    save(fullSavePath, 'expResults');
    fprintf('>>> 所有配置、时间戳与行为学数据已保存至: %s\n\n', fullSavePath);

    Screen('TextSize', window, 50);
    DrawFormattedText(window, double(char(EndText)), 'center', 'center', [1 1 1]);
    Screen('Flip', window); 
    wait_for_key(space_key, esc_key);

    ListenChar(0); KbQueueRelease; sca;
    PsychPortAudio('Close', pahandle);
    if exist('Obj', 'var') && ~isempty(Obj)
        try fclose(Obj); delete(Obj); clear Obj; catch; end
    end

catch ME
    ListenChar(0); try KbQueueRelease; catch; end; sca;
    try PsychPortAudio('Close'); catch; end
    if exist('Obj', 'var') && ~isempty(Obj)
        try fclose(Obj); delete(Obj); clear global Obj; disp('⚠️ 串口已自动释放！'); catch; end
    end
    rethrow(ME);
end

% ---------------------------------------------------------
% 辅助函数
% ---------------------------------------------------------
function wait_for_key(target, esc)
    KbQueueFlush([]);
    while true
        [pressed, firstPress] = KbQueueCheck([]);
        if pressed
            if firstPress(esc) > 0, error('>>> 实验被用户终止 (ESC) <<<'); end
            if firstPress(target) > 0, break; end
        end
        WaitSecs(0.005);
    end
end

function send_trigger(trigger)
global Obj
if isempty(Obj) || ~isvalid(Obj), return; end
hex_trigger = dec2hex(trigger);
if trigger < 16, hex_trigger = ['0', hex_trigger]; end
trig_left = hex2dec([hex_trigger; '55'; '66'; '0D']);
try fwrite(Obj, trig_left); catch; write(Obj, trig_left, "uint8"); end
end
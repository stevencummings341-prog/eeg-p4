%% generate_questions_db.m
% 这是一个独立脚本，用于将 JSON 题库转为 MATLAB 原生结构体并保存

clear; clc;

% 1. 读取并解析刚才准备好的 JSON 题库
jsonPath = 'Questions.json'; % 确保路径和文件名对应
fid = fopen(jsonPath, 'r', 'n', 'UTF-8');
if fid == -1
    error('找不到 JSON 文件，请检查路径。');
end
rawText = fread(fid, '*char')';
fclose(fid);

questionData = jsondecode(rawText);

% 2. 提取所有的 ID 列表 (主程序检索题目的钥匙)
all_ids = {questionData.id};

% 3. 保存为 MAT 文件
savePath = 'QuestionsDB.mat';
save(savePath, 'questionData', 'all_ids');

fprintf('>>> 成功！JSON 题库已转换为 MAT 文件并保存至:\n%s\n', fullfile(pwd, savePath));
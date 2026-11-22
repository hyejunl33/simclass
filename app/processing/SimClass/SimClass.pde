import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.concurrent.LinkedBlockingQueue;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.Clip;
import javax.sound.sampled.DataLine;
import javax.sound.sampled.TargetDataLine;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import processing.data.JSONArray;
import processing.data.JSONObject;

// SimClass — Processing client
// 40-minute lesson rehearsal: HWP lesson plan, 3 personas, voice turns, BKT bars,
// phase timer, session end, and transcript + KT replay.

String SERVER_BASE = "http://127.0.0.1:8010";
String REPORT_DIR = System.getProperty("user.home") + "/SimClassReports";
String lessonId = "objects-meaning";
String lessonTopic = "물건의 의미는 무엇일까요?";
String lessonSummary = "HWP를 불러오면 수업안 요약이 표시됩니다.";

String input = "";
String status = "HWP를 불러오거나 [수업 시작]을 누르세요.";
ArrayList<String> misconceptionOptions = new ArrayList<String>();
ArrayList<String> misconceptionIds = new ArrayList<String>();
LinkedBlockingQueue<String> ttsQueue = new LinkedBlockingQueue<String>();
boolean sending = false;
boolean recording = false;
float lastAudioSec = 0;
boolean advancing = false;
boolean lastAdvanceFailed = false;
long lastAdvanceAttemptMs = 0;
VoiceRecorder recorder;

ArrayList<StudentView> students = new ArrayList<StudentView>();
ArrayList<String> transcript = new ArrayList<String>();
ArrayList<PhaseView> phases = new ArrayList<PhaseView>();

String sessionId = "";
boolean sessionStarted = false;
boolean sessionEnded = false;
long sessionStartMs = 0;
long phaseAnchorMs = 0;
int phaseIndex = 0;

boolean replayMode = false;
boolean feedbackMode = false;
boolean judging = false;
String feedbackSummary = "";
String reportTextPath = "";
ArrayList<FeedbackDomain> feedbackDomains = new ArrayList<FeedbackDomain>();
ArrayList<ReplayEntry> replayEntries = new ArrayList<ReplayEntry>();
ArrayList<String> replaySummary = new ArrayList<String>();
ArrayList<String> replayKt = new ArrayList<String>();
int replayScroll = 0;

void setup() {
  size(1100, 720);
  textFont(createFont("SansSerif", 16));
  String[] cfg = loadStrings("server.txt");
  if (cfg != null && cfg.length > 0 && cfg[0].trim().length() > 0) {
    SERVER_BASE = cfg[0].trim();
  }

  defaultPhases();
  students.add(new StudentView("harin", "하린", "", "국어사전 뜻", "confused"));
  students.add(new StudentView("junseo", "준서", "", "비싼 것", "thinking"));
  students.add(new StudentView("minji", "민지", "", "같은 순서 친구", "confused"));

  new Thread(() -> {
    while (true) {
      try {
        playTTS(ttsQueue.take());
      } catch (InterruptedException ignored) {
      }
    }
  }).start();

  refreshLessonAsync();
}

void defaultPhases() {
  phases.clear();
  phases.add(new PhaseView("intro", "학습 문제 확인", 5));
  phases.add(new PhaseView("concept", "개념 형성", 17));
  phases.add(new PhaseView("interpretation", "자료 해석", 12));
  phases.add(new PhaseView("application", "원리 적용", 6));
}

float elapsedSec() {
  if (!sessionStarted) return 0;
  return (millis() - sessionStartMs) / 1000.0;
}

float phaseElapsedSec() {
  if (!sessionStarted) return 0;
  return (millis() - phaseAnchorMs) / 1000.0;
}

int totalPlannedSec() {
  int total = 0;
  for (PhaseView p : phases) total += p.minutes * 60;
  return total == 0 ? 2400 : total;
}

PhaseView currentPhase() {
  if (phases.size() == 0) return new PhaseView("", "수업", 40);
  return phases.get(constrain(phaseIndex, 0, phases.size() - 1));
}

void draw() {
  background(247, 248, 250);
  autoAdvance();

  // Header
  fill(30, 35, 45);
  textSize(24);
  text("SimClass · 즐생 수업 리허설", 36, 48);

  drawButton(560, 22, 150, 42, startButtonLabel(), !(sessionStarted && !sessionEnded));
  drawButton(720, 22, 150, 42, recording ? "녹음 중... 놓으세요" : "음성 입력 (hold)",
      isSessionRunning(), recording ? color(210, 40, 40) : color(245, 247, 250),
      recording ? color(255) : color(40, 45, 55));
  drawButton(880, 22, 184, 42, "HWP 수업안 불러오기", true);

  // Lesson / phase line
  fill(70, 78, 90);
  textSize(15);
  text(lessonTopic, 36, 78, 570, 22);
  fill(90, 98, 110);
  textSize(13);
  PhaseView phase = currentPhase();
  text("Phase " + (phaseIndex + 1) + "/" + phases.size() + " · " + phase.name, 610, 78, 300, 20);

  fill(sessionEnded ? color(60, 140, 100) : color(50, 90, 180));
  textSize(13);
  String timer = formatClock(elapsedSec()) + " / " + formatClock(totalPlannedSec());
  text(timer, 890, 78, 174, 20);

  // Overall progress bar
  fill(228, 232, 238);
  rect(36, 96, 1028, 6, 3);
  float progress = constrain(elapsedSec() / (float) totalPlannedSec(), 0, 1);
  fill(sessionEnded ? color(60, 140, 100) : color(80, 130, 220));
  rect(36, 96, 1028 * progress, 6, 3);

  drawStudents();
  if (feedbackMode) {
    drawFeedback();
  } else if (replayMode) {
    drawReplay();
  } else {
    drawConversation();
  }
  drawInput();

  fill(120, 128, 140);
  textSize(12);
  text(status, 36, 704);
}

String startButtonLabel() {
  if (sessionEnded) return "새 세션";
  if (sessionStarted) return "수업 중";
  return "수업 시작";
}

boolean isSessionRunning() {
  return sessionStarted && !sessionEnded && !replayMode;
}

void drawButton(float x, float y, float w, float h, String label, boolean enabled) {
  drawButton(x, y, w, h, label, enabled, color(245, 247, 250), color(45, 55, 70));
}

void drawButton(
    float x, float y, float w, float h, String label, boolean enabled,
    color bg, color fg) {
  fill(enabled ? bg : color(238, 240, 244));
  stroke(200, 205, 215);
  strokeWeight(1);
  rect(x, y, w, h, 10);
  noStroke();
  fill(enabled ? fg : color(160, 166, 176));
  textSize(14);
  text(label, x + 14, y + h / 2 + 5);
}

void drawStudents() {
  for (int i = 0; i < students.size(); i++) {
    StudentView s = students.get(i);
    float x = 36 + i * 350;
    float y = 116;
    float w = 320;
    float h = 142;

    fill(255);
    stroke(225, 228, 234);
    strokeWeight(1);
    rect(x, y, w, h, 14);

    noStroke();
    fill(30, 35, 45);
    textSize(20);
    text(s.name, x + 20, y + 32);

    fill(stateColor(s.state));
    textSize(13);
    text(s.state, x + 20, y + 55);

    fill(90, 98, 110);
    textSize(13);
    text("오개념: " + shorten(s.misconception, 24), x + 20, y + 80);
    text("mastery: " + nf(s.mastery, 1, 2), x + 20, y + 102);

    fill(232, 235, 240);
    rect(x + 20, y + 114, w - 40, 8, 4);
    fill(80, 130, 220);
    rect(x + 20, y + 114, (w - 40) * constrain(s.mastery, 0, 1), 8, 4);
  }
}

void drawConversation() {
  fill(255);
  stroke(225, 228, 234);
  rect(36, 280, 1028, 330, 14);
  noStroke();
  fill(30, 35, 45);
  textSize(18);
  text("수업 대화", 56, 314);

  drawButton(738, 288, 92, 30, "다음 단계", isSessionRunning());
  drawButton(838, 288, 92, 30, "수업 종료", isSessionRunning());
  drawButton(938, 288, 108, 30, "리플레이", sessionStarted);

  textSize(14);
  fill(70, 78, 90);
  float ty = 350;
  int start = max(0, transcript.size() - 11);
  for (int i = start; i < transcript.size(); i++) {
    text(transcript.get(i), 56, ty, 980, 40);
    ty += 22;
  }
}

void drawReplay() {
  fill(255);
  stroke(225, 228, 234);
  rect(36, 280, 1028, 400, 14);
  noStroke();
  fill(30, 35, 45);
  textSize(18);
  text("리플레이 · 수업 대화 + KT 타임라인", 56, 314);

  drawButton(728, 288, 100, 30, judging ? "판정 중..." : "피드백", !judging);
  drawButton(838, 288, 100, 30, "대화로", true);

  textSize(13);
  fill(70, 78, 90);
  float y = 344;
  for (int i = 0; i < replaySummary.size(); i++) {
    text(replaySummary.get(i), 56, y, 980, 20);
    y += 20;
  }

  y += 10;
  fill(50, 90, 180);
  textSize(13);
  text("KT 타임라인 (학생별 평균 mastery)", 56, y);
  y += 18;
  fill(70, 78, 90);
  for (int i = 0; i < replayKt.size(); i++) {
    text(replayKt.get(i), 56, y, 980, 18);
    y += 18;
  }

  y += 8;
  fill(30, 35, 45);
  textSize(13);
  text("대화", 56, y);
  y += 20;

  int visible = 7;
  replayScroll = constrain(replayScroll, 0, max(0, replayEntries.size() - visible));
  for (int i = replayScroll; i < min(replayEntries.size(), replayScroll + visible); i++) {
    ReplayEntry e = replayEntries.get(i);
    fill(e.teacher ? color(40, 60, 95) : color(70, 78, 90));
    text("[" + formatClock(e.t) + "] " + e.label + ": " + e.text, 56, y, 980, 18);
    y += 18;
  }
}

void drawFeedback() {
  fill(255);
  stroke(225, 228, 234);
  rect(36, 280, 1028, 400, 14);
  noStroke();
  fill(30, 35, 45);
  textSize(18);
  text("수업실연 피드백", 56, 314);

  drawButton(728, 288, 100, 30, "리플레이", true);
  drawButton(838, 288, 108, 30, "보고서 열기", reportTextPath != null && reportTextPath.length() > 0);

  fill(70, 78, 90);
  textSize(12);
  text(shorten(feedbackSummary, 110), 56, 340, 980, 20);

  float y = 372;
  for (int i = 0; i < feedbackDomains.size(); i++) {
    FeedbackDomain d = feedbackDomains.get(i);
    fill(30, 35, 45);
    textSize(14);
    text(d.name, 56, y);

    fill(scoreColor(d.score, d.status));
    rect(246, y - 14, 48, 20, 6);
    fill(255);
    textSize(12);
    text(d.status.equals("not_assessed") ? "N/A" : str(d.score), 258, y);

    fill(70, 78, 90);
    textSize(12);
    text(shorten(d.reason, 94), 320, y, 700, 18);
    if (d.evidence != null && d.evidence.length() > 0) {
      fill(110, 118, 130);
      text("증거: \"" + shorten(d.evidence, 88) + "\"", 320, y + 16, 700, 16);
    }
    y += 44;
  }

  fill(130, 138, 150);
  textSize(11);
  text("※ 공식 채점표가 아니라 대화록 증거 기반 보조 피드백입니다. 전달 태도·시선·제스처는 N/A입니다.", 56, 662);
}

color scoreColor(int score, String status) {
  if ("not_assessed".equals(status)) return color(150, 156, 166);
  if (score >= 3) return color(60, 140, 100);
  if (score == 2) return color(60, 110, 200);
  if (score == 1) return color(200, 140, 40);
  return color(190, 80, 70);
}

void drawInput() {
  if (replayMode || feedbackMode) return;
  boolean active = isSessionRunning();
  fill(active ? color(255) : color(243, 245, 248));
  stroke(200, 205, 215);
  rect(36, 632, 860, 48, 10);
  noStroke();
  fill(active ? color(30, 35, 45) : color(160, 166, 176));
  textSize(16);
  if (active) {
    text(input + (frameCount / 30 % 2 == 0 ? "|" : ""), 52, 662);
  } else {
    text(sessionEnded ? "수업이 끝났습니다. [리플레이] 또는 [새 세션]을 선택하세요." : "수업을 시작하면 발문을 입력할 수 있습니다.", 52, 662);
  }

  drawButton(910, 632, 154, 48,
      sending ? "전송 중..." : "발문 전송", active && !sending, color(50, 90, 180), color(255));
}

void autoAdvance() {
  if (!isSessionRunning() || advancing) return;
  long now = millis();
  if (now - lastAdvanceAttemptMs < 2000) return;
  PhaseView p = currentPhase();
  if (phaseElapsedSec() < p.minutes * 60) return;
  if (phaseIndex >= phases.size() - 1) {
    endSession(true);
    return;
  }
  advancePhase();
}

void keyTyped() {
  if (!isSessionRunning()) return;
  if (key == ENTER || key == RETURN) {
    sendTurn();
  } else if (key == BACKSPACE) {
    if (input.length() > 0) input = input.substring(0, input.length() - 1);
  } else if (key != CODED && key != TAB) {
    input += key;
  }
}

void mousePressed() {
  // Start / new session
  if (mouseX > 560 && mouseX < 710 && mouseY > 22 && mouseY < 64) {
    if (!sessionStarted || sessionEnded) startSession();
    return;
  }
  if (mouseX > 720 && mouseX < 870 && mouseY > 22 && mouseY < 64) {
    if (isSessionRunning()) startRecording();
    else status = "수업을 시작한 뒤 음성을 사용할 수 있습니다.";
    return;
  }
  if (mouseX > 880 && mouseX < 1064 && mouseY > 22 && mouseY < 64) {
    selectInput("HWP 수업안 선택", "hwpSelected");
    return;
  }

  // Session controls in the conversation header
  if (mouseY > 288 && mouseY < 318) {
    if (feedbackMode) {
      if (mouseX > 728 && mouseX < 828) {
        feedbackMode = false;
        replayMode = true;
        return;
      }
      if (mouseX > 838 && mouseX < 938) {
        if (reportTextPath != null && reportTextPath.length() > 0) {
          launch(reportTextPath);
          status = "보고서를 엽니다: " + reportTextPath;
        } else {
          status = "저장된 보고서가 없습니다.";
        }
        return;
      }
      return;
    }
    if (replayMode) {
      if (mouseX > 728 && mouseX < 828) {
        requestJudge();
      } else if (mouseX > 838 && mouseX < 938) {
        replayMode = false;
      }
      return;
    }
    if (mouseX > 738 && mouseX < 830) {
      if (isSessionRunning()) advancePhase();
      return;
    }
    if (mouseX > 838 && mouseX < 930) {
      if (isSessionRunning()) endSession(true);
      return;
    }
    if (mouseX > 938 && mouseX < 1046) {
      if (sessionStarted) {
        endSession(true);
      } else {
        status = "수업을 시작한 뒤 리플레이할 수 있습니다.";
      }
      return;
    }
  }

  // Click a student card to cycle its misconception.
  if (mouseY > 116 && mouseY < 258) {
    int idx = floor((mouseX - 36) / 350);
    if (idx >= 0 && idx < students.size() && misconceptionOptions.size() > 0) {
      StudentView s = students.get(idx);
      int current = misconceptionOptions.indexOf(s.misconception);
      int next = (current + 1) % misconceptionOptions.size();
      s.misconception = misconceptionOptions.get(next);
      if (next < misconceptionIds.size()) s.misconceptionId = misconceptionIds.get(next);
      savePersonas();
      status = s.name + "의 오개념을 바꿨습니다.";
      return;
    }
  }

  if (mouseX > 910 && mouseX < 1064 && mouseY > 632 && mouseY < 680) {
    if (isSessionRunning() && !sending) sendTurn();
  }
}

void mouseReleased() {
  if (recording && mouseButton == LEFT) {
    stopRecordingAndSend();
  }
}

void mouseWheel(processing.event.MouseEvent event) {
  if (!replayMode) return;
  replayScroll += event.getCount() * 3;
  replayScroll = constrain(replayScroll, 0, max(0, replayEntries.size() - 7));
}

void startSession() {
  replayMode = false;
  feedbackMode = false;
  feedbackDomains.clear();
  feedbackSummary = "";
  reportTextPath = "";
  transcript.clear();
  replayEntries.clear();
  replaySummary.clear();
  replayKt.clear();
  sessionId = "demo-" + System.currentTimeMillis();
  phaseIndex = 0;
  sessionEnded = false;
  input = "";
  lastAudioSec = 0;
  status = "세션을 시작하는 중...";

  new Thread(() -> {
    try {
      JSONObject payload = new JSONObject();
      payload.setString("lesson_id", lessonId);
      payload.setString("session_id", sessionId);
      JSONObject res = parseJSONObject(postJson(SERVER_BASE + "/api/session/start", payload.toString()));
      phaseIndex = res.getInt("phase_index");
      sessionStartMs = millis();
      phaseAnchorMs = sessionStartMs;
      sessionStarted = true;
      status = "수업 시작 · " + res.getString("phase_name") + " (" + res.getInt("phase_planned_min") + "분)";
      transcript.add("[수업 시작] " + lessonTopic);
    } catch (Exception e) {
      status = "세션 시작 실패: " + e.getMessage();
    }
  }).start();
}

void advancePhase() {
  if (!sessionStarted || sessionEnded || advancing) return;
  advancing = true;
  lastAdvanceAttemptMs = millis();
  status = "다음 단계로 이동하는 중...";

  new Thread(() -> {
    try {
      JSONObject res = parseJSONObject(
          postJson(SERVER_BASE + "/api/session/" + sessionId + "/advance", "{}"));
      int nextIndex = res.getInt("phase_index");
      phaseIndex = nextIndex;
      phaseAnchorMs = millis();
      lastAdvanceFailed = false;
      status = "단계 이동 · " + res.getString("phase_name") + " (" + res.getInt("phase_remaining_sec") + "초 남음)";
      transcript.add("[단계] " + res.getString("phase_name"));
    } catch (Exception e) {
      lastAdvanceFailed = true;
      String msg = e.getMessage() == null ? "" : e.getMessage();
      if (msg.contains("HTTP 404") || msg.contains("HTTP 409")) {
        sessionEnded = true;
        status = "세션이 종료되었습니다. 새 세션을 시작하세요.";
      } else {
        status = "단계 이동 실패: " + msg;
      }
    } finally {
      advancing = false;
    }
  }).start();
}

void endSession(boolean loadReplayAfter) {
  if (!sessionStarted || sessionEnded || advancing) return;
  advancing = true;
  status = "수업을 정리하는 중...";

  new Thread(() -> {
    try {
      JSONObject summary = parseJSONObject(
          postJson(SERVER_BASE + "/api/session/" + sessionId + "/end", "{}"));
      sessionEnded = true;
      status = "수업 종료 · " + formatClock(summary.getFloat("elapsed_sec"))
          + " · 발문 " + summary.getInt("turns") + "회";
      if (loadReplayAfter) loadReplay();
    } catch (Exception e) {
      String msg = e.getMessage() == null ? "" : e.getMessage();
      if (msg.contains("HTTP 404") || msg.contains("HTTP 409")) {
        sessionEnded = true;
        status = "세션이 종료되었습니다. 새 세션을 시작하세요.";
      } else {
        status = "수업 종료 실패: " + msg;
      }
    } finally {
      advancing = false;
    }
  }).start();
}

void loadReplay() {
  try {
    JSONObject rep = parseJSONObject(
        getJson(SERVER_BASE + "/api/session/" + sessionId + "/replay"));
    replayEntries.clear();
    replaySummary.clear();
    replayKt.clear();

    float duration = rep.getFloat("duration_sec");
    float planned = rep.getFloat("planned_sec");
    JSONArray tr = rep.getJSONArray("transcript");
    int teacherTurns = 0;
    int studentTurns = 0;
    for (int i = 0; i < tr.size(); i++) {
      JSONObject e = tr.getJSONObject(i);
      boolean isTeacher = "teacher".equals(e.getString("speaker"));
      if (isTeacher) teacherTurns++;
      else studentTurns++;
      String label = e.getString("name");
      if (label == null || label.length() == 0) label = isTeacher ? "교사" : "학생";
      replayEntries.add(new ReplayEntry(e.getFloat("t"), label, e.getString("text"), isTeacher));
    }
    replaySummary.add("총 " + formatClock(duration) + " / 계획 " + formatClock(planned)
        + " · 발문 " + teacherTurns + "회 · 학생 응답 " + studentTurns + "회");

    JSONArray ph = rep.getJSONArray("phases");
    for (int i = 0; i < ph.size(); i++) {
      JSONObject p = ph.getJSONObject(i);
      replaySummary.add(p.getString("name") + "  계획 " + p.getInt("planned_min") + "분 · 실제 "
          + formatClock(p.getFloat("actual_sec")) + " · 발화 " + p.getInt("entries") + "개");
    }

    JSONArray kt = rep.getJSONArray("kt_timeline");
    int from = max(0, kt.size() - 3);
    for (int i = from; i < kt.size(); i++) {
      JSONObject snap = kt.getJSONObject(i);
      JSONObject ktm = snap.getJSONObject("kt");
      replayKt.add("[" + formatClock(snap.getFloat("t")) + "] " + ktLine(ktm));
    }
    if (kt.size() == 0) replayKt.add("기록된 KT 변화가 없습니다.");

    replayScroll = 0;
    replayMode = true;
  } catch (Exception e) {
    status = "리플레이 불러오기 실패: " + e.getMessage();
  }
}

void requestJudge() {
  if (!sessionStarted || judging) return;
  if (!sessionEnded) {
    endSession(true);
    status = "수업을 종료한 뒤 피드백을 생성합니다.";
    return;
  }
  judging = true;
  status = "피드백 생성 중... (7B judge, 30~90초)";

  new Thread(() -> {
    try {
      JSONObject rep = parseJSONObject(
          postJson(SERVER_BASE + "/api/session/" + sessionId + "/judge", "{}"));
      ArrayList<FeedbackDomain> list = new ArrayList<FeedbackDomain>();
      JSONArray arr = rep.getJSONArray("domains");
      for (int i = 0; i < arr.size(); i++) {
        JSONObject d = arr.getJSONObject(i);
        String status = d.getString("status");
        int score = d.isNull("score") ? -1 : d.getInt("score");
        String evidence = "";
        JSONArray ev = d.getJSONArray("evidence");
        if (ev != null && ev.size() > 0) {
          evidence = ev.getJSONObject(0).getString("quote");
        }
        list.add(new FeedbackDomain(
            d.getString("name"), score, status,
            d.getString("reason"), d.getString("improvement"), evidence));
      }
      String md = getJson(SERVER_BASE + "/api/session/" + sessionId + "/report.md");
      new java.io.File(REPORT_DIR).mkdirs();
      String path = REPORT_DIR + "/report-" + sessionId + ".md";
      saveStrings(path, split(md, "\n"));

      feedbackDomains = list;
      feedbackSummary = rep.getString("summary");
      reportTextPath = path;
      replayMode = false;
      feedbackMode = true;
      status = "피드백 생성 완료 · 보고서 저장: " + path;
    } catch (Exception e) {
      status = "피드백 생성 실패: " + e.getMessage();
    } finally {
      judging = false;
    }
  }).start();
}

String ktLine(JSONObject ktMap) {
  StringBuilder sb = new StringBuilder();
  for (StudentView s : students) {
    try {
      JSONObject m = ktMap.getJSONObject(s.id);
      if (m != null) {
        if (sb.length() > 0) sb.append(" · ");
        sb.append(s.name).append(" ").append(nf(avgMastery(m), 1, 2));
      }
    } catch (Exception ignored) {}
  }
  return sb.toString();
}

void refreshLessonAsync() {
  new Thread(() -> {
    try {
      JSONObject lesson = parseJSONObject(getJson(SERVER_BASE + "/api/lesson/" + lessonId));
      applyLesson(lesson);
      JSONObject ps = parseJSONObject(getJson(SERVER_BASE + "/api/personas/" + lessonId));
      applyPersonas(ps.getJSONArray("personas"));
      status = "서버 연결됨 · 수업을 시작할 수 있습니다.";
    } catch (Exception e) {
      status = "서버 대기 중 · " + e.getMessage();
    }
  }).start();
}

void applyLesson(JSONObject lesson) {
  lessonId = lesson.getString("id");
  lessonTopic = lesson.getString("topic");
  JSONArray arr = lesson.getJSONArray("phases");
  int minutes = lesson.getInt("duration_min");
  lessonSummary = arr.size() + "단계 · " + minutes + "분 · 학생 3명";
  phases.clear();
  for (int i = 0; i < arr.size(); i++) {
    JSONObject p = arr.getJSONObject(i);
    phases.add(new PhaseView(p.getString("id"), p.getString("name"), p.getInt("minutes")));
  }
  if (phases.size() == 0) defaultPhases();
}

void applyPersonas(JSONArray ps) {
  students.clear();
  for (int i = 0; i < ps.size(); i++) {
    JSONObject p = ps.getJSONObject(i);
    StudentView sv = new StudentView(
        p.getString("id"),
        p.getString("name"),
        p.getString("misconception_id"),
        p.getString("misconception"),
        "thinking");
    sv.priorKnowledge = p.getString("prior_knowledge");
    sv.confidence = p.getString("confidence");
    sv.speechStyle = p.getString("speech_style");
    try {
      sv.initialMastery = p.getJSONObject("initial_mastery");
      if (sv.initialMastery == null) sv.initialMastery = new JSONObject();
    } catch (Exception ignored) {
      sv.initialMastery = new JSONObject();
    }
    sv.mastery = avgMastery(sv.initialMastery);
    students.add(sv);
  }
}

void hwpSelected(File selection) {
  if (selection == null) return;
  status = "HWP를 읽는 중...";
  new Thread(() -> {
    try {
      byte[] bytes = loadBytes(selection.getAbsolutePath());
      String encoded = Base64.getEncoder().encodeToString(bytes);
      JSONObject payload = new JSONObject();
      payload.setString("filename", selection.getName());
      payload.setString("data_base64", encoded);
      String response = postJson(SERVER_BASE + "/api/lesson/ingest", payload.toString());
      JSONObject lesson = parseJSONObject(response);
      applyLesson(lesson);

      sessionStarted = false;
      sessionEnded = false;
      replayMode = false;
      feedbackMode = false;
      lastAudioSec = 0;
      feedbackDomains.clear();
      feedbackSummary = "";
      reportTextPath = "";
      sessionId = "";
      phaseIndex = 0;
      transcript.clear();

      // Refresh misconception choices and generate personas.
      misconceptionOptions.clear();
      misconceptionIds.clear();
      JSONArray ms = lesson.getJSONArray("misconceptions");
      for (int i = 0; i < ms.size(); i++) {
        JSONObject m = ms.getJSONObject(i);
        misconceptionOptions.add(m.getString("text"));
        misconceptionIds.add(m.getString("id"));
      }
      JSONObject pReq = new JSONObject();
      pReq.setString("lesson_id", lessonId);
      JSONObject pRes = parseJSONObject(
          postJson(SERVER_BASE + "/api/personas/generate", pReq.toString()));
      applyPersonas(pRes.getJSONArray("personas"));

      status = "수업안 파싱 완료" + (lesson.getBoolean("needs_review") ? " · 검토 필요" : "");
      transcript.add("[수업안] " + lessonTopic);
    } catch (Exception e) {
      status = "HWP 파싱 실패: " + e.getMessage();
    }
  }).start();
}

void savePersonas() {
  if (students.size() == 0) return;
  try {
    JSONObject payload = new JSONObject();
    payload.setString("lesson_id", lessonId);
    JSONArray arr = new JSONArray();
    for (int i = 0; i < students.size(); i++) {
      StudentView s = students.get(i);
      JSONObject p = new JSONObject();
      p.setString("id", s.id);
      p.setString("name", s.name);
      p.setString("prior_knowledge", s.priorKnowledge);
      p.setString("misconception_id", s.misconceptionId);
      p.setString("misconception", s.misconception);
      p.setString("confidence", s.confidence);
      p.setString("speech_style", s.speechStyle);
      p.setJSONObject("initial_mastery", s.initialMastery);
      arr.append(p);
    }
    payload.setJSONArray("personas", arr);
    requestJson("PUT", SERVER_BASE + "/api/personas/" + lessonId, payload.toString());
  } catch (Exception e) {
    status = "페르소나 저장 실패: " + e.getMessage();
  }
}

void startRecording() {
  if (recording) return;
  try {
    recorder = new VoiceRecorder();
    recorder.start();
    recording = true;
    status = "녹음 중... 버튼을 놓으면 전송합니다.";
  } catch (Exception e) {
    status = "마이크 오류: " + e.getMessage();
  }
}

void stopRecordingAndSend() {
  if (!recording || recorder == null) return;
  recording = false;
  try {
    byte[] wav = recorder.stop();
    String encoded = Base64.getEncoder().encodeToString(wav);
    JSONObject payload = new JSONObject();
    payload.setString("filename", "teacher.wav");
    payload.setString("data_base64", encoded);
    new Thread(() -> {
      try {
        JSONObject res = parseJSONObject(postJson(SERVER_BASE + "/api/asr", payload.toString()));
        String text = res.getString("text");
        input = text;
        lastAudioSec = res.isNull("duration_sec") ? 0 : res.getFloat("duration_sec");
        transcript.add("[음성] " + text);
        status = "음성 인식 완료 (" + res.getString("mode") + ")";
        sendTurn();
      } catch (Exception e) {
        status = "ASR 실패: " + e.getMessage();
      }
    }).start();
  } catch (Exception e) {
    status = "녹음 종료 실패: " + e.getMessage();
  }
}

void speak(String text) {
  ttsQueue.offer(text);
}

void playTTS(String text) {
  try {
    JSONObject payload = new JSONObject();
    payload.setString("text", text);
    byte[] audio = requestBytes(SERVER_BASE + "/api/tts", payload.toString());
    if (audio.length == 0) return;
    AudioInputStream ais = AudioSystem.getAudioInputStream(new ByteArrayInputStream(audio));
    Clip clip = AudioSystem.getClip();
    clip.open(ais);
    clip.start();
    Thread.sleep(clip.getMicrosecondLength() / 1000 + 150);
    clip.close();
  } catch (Exception ignored) {
  }
}

void sendTurn() {
  String utterance = input.trim();
  if (utterance.length() == 0 || sending) return;
  input = "";
  sending = true;
  float audioSec = lastAudioSec;
  lastAudioSec = 0;
  status = "서버에 발문을 보내는 중...";
  transcript.add("T: " + utterance);

  String phaseId = currentPhase().id;
  new Thread(() -> {
    try {
      JSONObject payload = new JSONObject();
      payload.setString("session_id", sessionId);
      payload.setString("lesson_id", lessonId);
      payload.setString("phase_id", phaseId);
      payload.setString("teacher_utterance", utterance);
      payload.setFloat("audio_sec", audioSec);
      String response = postJson(SERVER_BASE + "/api/turn", payload.toString());
      JSONObject res = parseJSONObject(response);
      JSONArray arr = res.getJSONArray("students");
      for (int i = 0; i < arr.size(); i++) {
        JSONObject s = arr.getJSONObject(i);
        String name = s.getString("name");
        String text = s.getString("text");
        String state = s.getString("state");
        transcript.add(name + ": " + text);
        speak(text);
        for (StudentView sv : students) {
          if (sv.id.equals(s.getString("id"))) {
            sv.state = state;
            try {
              JSONObject m = s.getJSONObject("mastery");
              if (m != null) {
                sv.initialMastery = m;
                sv.mastery = avgMastery(m);
              }
            } catch (Exception ignored) {}
          }
        }
      }
      status = "응답 도착 · " + res.getString("mode") + " · " + currentPhase().name;
    } catch (Exception e) {
      status = "연결 실패: " + e.getMessage();
    } finally {
      sending = false;
    }
  }).start();
}

String postJson(String url, String body) throws Exception {
  return requestJson("POST", url, body);
}

String getJson(String url) throws Exception {
  return requestJson("GET", url, null);
}

String requestJson(String method, String url, String body) throws Exception {
  HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
  conn.setRequestMethod(method);
  conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
  if (body != null) {
    conn.setDoOutput(true);
    byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
    try (OutputStream os = conn.getOutputStream()) {
      os.write(bytes);
    }
  }
  int code = conn.getResponseCode();
  if (code != 200) {
    String detail = "";
    try (InputStream es = conn.getErrorStream()) {
      if (es != null) {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] tmp = new byte[4096];
        int n;
        while ((n = es.read(tmp)) > 0) buf.write(tmp, 0, n);
        detail = new String(buf.toByteArray(), StandardCharsets.UTF_8);
      }
    } catch (Exception ignored) {}
    throw new RuntimeException("HTTP " + code + (detail.length() > 0 ? ": " + detail : ""));
  }
  StringBuilder sb = new StringBuilder();
  try (BufferedReader br = new BufferedReader(
      new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
    String line;
    while ((line = br.readLine()) != null) sb.append(line).append('\n');
  }
  return sb.toString();
}

byte[] requestBytes(String url, String body) throws Exception {
  HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
  conn.setRequestMethod("POST");
  conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
  conn.setDoOutput(true);
  try (OutputStream os = conn.getOutputStream()) {
    os.write(body.getBytes(StandardCharsets.UTF_8));
  }
  int code = conn.getResponseCode();
  if (code == 204) return new byte[0];
  if (code != 200) throw new RuntimeException("HTTP " + code);
  ByteArrayOutputStream out = new ByteArrayOutputStream();
  try (InputStream in = conn.getInputStream()) {
    byte[] buf = new byte[8192];
    int n;
    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
  }
  return out.toByteArray();
}

float avgMastery(JSONObject m) {
  if (m == null) return 0;
  float sum = 0;
  int n = 0;
  for (Object key : m.keys()) {
    sum += m.getFloat((String) key);
    n++;
  }
  return n == 0 ? 0 : sum / n;
}

String shorten(String s, int maxLen) {
  if (s == null) return "";
  return s.length() <= maxLen ? s : s.substring(0, maxLen - 1) + "…";
}

String formatClock(float seconds) {
  int total = max(0, round(seconds));
  int m = total / 60;
  int s = total % 60;
  return nf(m, 2) + ":" + nf(s, 2);
}

color stateColor(String state) {
  if (state == null) return color(60, 140, 100);
  if (state.equals("confused")) return color(200, 90, 80);
  if (state.equals("thinking")) return color(190, 140, 40);
  return color(60, 140, 100);
}

class PhaseView {
  String id;
  String name;
  int minutes;

  PhaseView(String id, String name, int minutes) {
    this.id = id;
    this.name = name;
    this.minutes = minutes;
  }
}

class FeedbackDomain {
  String name;
  int score;
  String status;
  String reason;
  String improvement;
  String evidence;

  FeedbackDomain(
      String name, int score, String status,
      String reason, String improvement, String evidence) {
    this.name = name;
    this.score = score;
    this.status = status;
    this.reason = reason;
    this.improvement = improvement;
    this.evidence = evidence;
  }
}

class ReplayEntry {
  float t;
  String label;
  String text;
  boolean teacher;

  ReplayEntry(float t, String label, String text, boolean teacher) {
    this.t = t;
    this.label = label;
    this.text = text;
    this.teacher = teacher;
  }
}

class VoiceRecorder {
  AudioFormat format;
  TargetDataLine line;
  ByteArrayOutputStream pcm;
  Thread thread;
  volatile boolean running;

  void start() throws Exception {
    format = new AudioFormat(16000, 16, 1, true, false);
    DataLine.Info info = new DataLine.Info(TargetDataLine.class, format);
    line = (TargetDataLine) AudioSystem.getLine(info);
    line.open(format);
    line.start();
    pcm = new ByteArrayOutputStream();
    running = true;
    thread = new Thread(() -> {
      byte[] buf = new byte[4096];
      while (running) {
        int n = line.read(buf, 0, buf.length);
        if (n > 0) pcm.write(buf, 0, n);
      }
    });
    thread.start();
  }

  byte[] stop() throws Exception {
    running = false;
    line.stop();
    line.close();
    thread.join(800);
    byte[] raw = pcm.toByteArray();
    AudioInputStream ais = new AudioInputStream(
        new ByteArrayInputStream(raw), format, raw.length / format.getFrameSize());
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    AudioSystem.write(ais, AudioFileFormat.Type.WAVE, out);
    return out.toByteArray();
  }
}

class StudentView {
  String id;
  String name;
  String misconceptionId;
  String misconception;
  String state;
  float mastery;
  JSONObject initialMastery = new JSONObject();
  String priorKnowledge = "중간";
  String confidence = "중간";
  String speechStyle = "";

  StudentView(String id, String name, String misconceptionId, String misconception, String state) {
    this.id = id;
    this.name = name;
    this.misconceptionId = misconceptionId;
    this.misconception = misconception;
    this.state = state;
  }
}

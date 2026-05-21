// Prevent the Windows console window from opening in --release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    fly_video_automation_lib::run();
}

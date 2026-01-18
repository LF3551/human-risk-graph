# Creating GitHub Release v0.1.0

The git tag has been pushed to GitHub. Now create the official Release:

## Steps:

1. **Go to GitHub Repository**:
   ```
   https://github.com/LF3551/human-risk-graph/releases/new
   ```

2. **Select Tag**: Choose `v0.1.0` from dropdown

3. **Release Title**: 
   ```
   v0.1.0 - Initial Public Release
   ```

4. **Description** (copy this):

```markdown
# 🎉 Human Risk Graph v0.1.0 - Initial Public Release

## 🚀 What is Human Risk Graph?

Human Risk Graph (HRG) is a **quantitative model** for measuring organizational security risk caused by human dependencies, decision concentration, and bus-factor effects.

Unlike traditional security models that focus only on technical assets, HRG treats **people as part of the attack surface** and models how organizational decisions and emergency processes introduce systemic risk.

---

## ✨ Key Features

### 🔧 Command-Line Interface
```bash
# Analyze organization and generate reports
hrg analyze data/organization.json

# Create interactive visualization
hrg visualize data/organization.json
```

### 📊 Three Core Risk Metrics
1. **Bus Factor Score** (40%): Measures fragility from key person dependencies
2. **Decision Concentration** (35%): Quantifies authority centralization 
3. **Bypass Risk** (25%): Evaluates control override risks

### 🎨 Interactive Visualization
- Beautiful HTML graphs with **pyvis**
- Risk-based color coding (cyan → orange → red)
- Hover tooltips with detailed metrics
- Real-time graph manipulation

### 📝 Professional Reports
- **JSON**: Machine-readable analysis
- **Markdown**: Documentation with recommendations
- **HTML**: Styled reports with dark theme

### 🧪 Quality Assurance
- ✅ 25 unit tests (100% passing)
- ✅ GitHub Actions CI/CD
- ✅ Multi-version Python support (3.8-3.12)
- ✅ Code quality: Black, flake8, mypy, bandit
- ✅ Security scanning

---

## 📦 Installation

```bash
# Clone repository
git clone https://github.com/LF3551/human-risk-graph.git
cd human-risk-graph

# Install
pip install -e .

# Run analysis
hrg analyze data/example_organization.json
```

---

## 🎯 Use Cases

- **CISSP Portfolio**: Demonstrate advanced security modeling
- **Risk Assessment**: Evaluate organizational dependencies
- **Research**: Academic study of human-centric security
- **Business Continuity**: Identify critical personnel
- **Succession Planning**: Model impact of key departures

---

## 📚 What's Included

- **Core Library**: Graph-based risk analysis engine
- **CLI Tool**: Professional command-line interface
- **Test Suite**: 25 comprehensive unit tests
- **Documentation**: Mathematical model + API docs
- **Academic Paper**: LaTeX source (arXiv-ready)
- **Experiments**: Synthetic data generator + benchmarks
- **Examples**: Usage demonstrations

---

## 🔬 Technical Highlights

### Algorithms
- Tarjan's Algorithm for articulation points (O(V+E))
- Critical path analysis for bypass detection
- Gini coefficient for concentration measurement
- Betweenness centrality for influence

### Dependencies
- NetworkX 3.0+ (graph operations)
- NumPy 1.24+ (numerical computing)
- SciPy 1.10+ (scientific algorithms)
- Click 8.1+ (CLI framework)
- pyvis 0.3.2+ (visualization)

---

## 📈 Example Output

```
🔍 Analyzing: organization.json
⚙️  Running Human Risk Graph analysis...
✅ Generated: report.json
✅ Generated: report.md
✅ Generated: report.html
✅ Generated: graph.html

============================================================
📊 ANALYSIS SUMMARY
============================================================
Composite HRG Score: 0.245
  • Bus Factor Score: 0.387
  • Decision Concentration: 0.156
  • Bypass Risk Score: 0.198

⚠️  Critical People (Articulation Points): 3
   - Alice (CTO)
   - Bob (Lead Engineer)
   - Carol (Security Manager)

✅ Analysis complete! Generated 4 file(s).
```

---

## 🛣️ Roadmap

### v0.2.0 (Planned)
- Web dashboard (Flask/FastAPI)
- LDAP/Active Directory integration
- Historical trend analysis
- Custom metric weights

### v0.3.0 (Planned)
- Machine learning predictions
- What-if scenario analysis
- SIEM integration
- Multi-organization comparison

---

## 👤 Author

**Aleksei Aleinikov**
- GitHub: [@LF3551](https://github.com/LF3551)
- Repository: [human-risk-graph](https://github.com/LF3551/human-risk-graph)

---

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE)

---

## 🙏 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## 📖 Citation

If you use this in research, please cite:

```bibtex
@software{aleinikov2026hrg,
  author = {Aleinikov, Aleksei},
  title = {Human Risk Graph: A Quantitative Model for Organizational Security Risk},
  year = {2026},
  version = {0.1.0},
  url = {https://github.com/LF3551/human-risk-graph}
}
```

---

## ⭐ Show Your Support

If you find this useful for your **CISSP portfolio** or **security research**, give it a star! ⭐

---

**Full Changelog**: https://github.com/LF3551/human-risk-graph/blob/main/CHANGELOG.md
```

5. **Assets to Upload** (optional but recommended):
   - Screenshots of HTML reports
   - Example graph visualizations
   - Demo GIF showing CLI in action

6. **Set as Latest Release**: ✅ Check this box

7. **Click "Publish Release"**

---

## Alternative: Use GitHub CLI

If you have `gh` CLI installed:

```bash
gh release create v0.1.0 \
  --title "v0.1.0 - Initial Public Release" \
  --notes-file .github/release-notes.md \
  --latest
```

---

## After Release

The release will be available at:
```
https://github.com/LF3551/human-risk-graph/releases/tag/v0.1.0
```

Users can install directly from the release:
```bash
pip install git+https://github.com/LF3551/human-risk-graph.git@v0.1.0
```

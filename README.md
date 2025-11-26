# Cursor Support Notes

A growing collection of troubleshooting tips, common issues, and user guidance for [Cursor](https://cursor.sh) — an AI-powered code editor for developers.

## Why this exists
As someone transitioning into technical support, I’m documenting real and simulated user issues to:
- Practice clear, empathetic technical communication  
- Build reusable knowledge for community support  
- Deepen my understanding of developer workflows

## Common Issues & Fixes

### 1. "Cursor doesn’t load my project context"
- ✅ **Check**: Is the folder opened as a workspace (not just a file)?  
- ✅ **Fix**: Close all files → Open folder via `File > Open Folder`  
- ✅ **Note**: Cursor works best at the **project root** level.

### 2. "Chat doesn’t understand my code"
- ✅ **Check**: Is the file saved and part of an open workspace?  
- ✅ **Tip**: Use `Cmd+K` to explicitly reference code in chat.

---

*Updated regularly. Open to feedback!*

### 3. "Cursor isn’t syncing with my GitHub repository"

- ✅ **Check**: Is GitHub connected in Cursor settings?  
  → Go to `Settings > Integrations > GitHub` and ensure your account is linked.

- ✅ **Check**: Are you using a **personal access token (PAT)** with correct scopes?  
  → Token must include: `repo`, `workflow`, `read:user`  
  → [GitHub guide to creating a PAT](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

- ✅ **Fix**: If sync fails after linking:  
  1. Revoke the old token in GitHub  
  2. Generate a new one with required scopes  
  3. Reconnect GitHub in Cursor

- ✅ **Note**: Private repositories require explicit token access. Public repos sync automatically once linked.

- 🛠️ **Debug tip**: Check `Help > Toggle Developer Tools > Console` for auth errors like `403 Forbidden`.

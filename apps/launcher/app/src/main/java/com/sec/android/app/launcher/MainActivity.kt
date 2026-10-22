package com.sec.android.app.launcher

import android.content.Intent
import android.content.pm.ResolveInfo
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView

data class AppModel(
    val label: String,
    val packageName: String,
    val icon: Drawable,
    val launchIntent: Intent
)

class MainActivity : AppCompatActivity() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: AppAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        recyclerView = findViewById(R.id.app_recycler_view)
        recyclerView.layoutManager = GridLayoutManager(this, 4)

        val installedApps = loadInstalledApps()
        adapter = AppAdapter(installedApps) { app ->
            startActivity(app.launchIntent)
        }
        recyclerView.adapter = adapter
    }

    private fun loadInstalledApps(): List<AppModel> {
        val mainIntent = Intent(Intent.ACTION_MAIN, null).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val resolveInfos: List<ResolveInfo> = packageManager.queryIntentActivities(mainIntent, 0)
        val apps = mutableListOf<AppModel>()

        for (ri in resolveInfos) {
            if (ri.activityInfo.packageName == packageName) continue

            val label = ri.loadLabel(packageManager).toString()
            val icon = ri.loadIcon(packageManager)
            val launchIntent = packageManager.getLaunchIntentForPackage(ri.activityInfo.packageName)

            if (launchIntent != null) {
                apps.add(AppModel(label, ri.activityInfo.packageName, icon, launchIntent))
            }
        }
        return apps.sortedBy { it.label }
    }
}

class AppAdapter(
    private val appList: List<AppModel>,
    private val onItemClick: (AppModel) -> Unit
) : RecyclerView.Adapter<AppAdapter.AppViewHolder>() {

    class AppViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val appIcon: ImageView = view.findViewById(R.id.app_icon)
        val appName: TextView = view.findViewById(R.id.app_name)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): AppViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_app, parent, false)
        return AppViewHolder(view)
    }

    override fun onBindViewHolder(holder: AppViewHolder, position: Int) {
        val app = appList[position]
        holder.appName.text = app.label
        holder.appIcon.setImageDrawable(app.icon)
        holder.itemView.setOnClickListener { onItemClick(app) }
    }

    override fun getItemCount(): Int = appList.size
}

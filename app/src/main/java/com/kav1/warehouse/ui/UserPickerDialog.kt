package com.kav1.warehouse.ui

import android.content.Context
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.UserEntity

/** "בחר חייל/גורם מאשר": searchable list of users. */
object UserPickerDialog {

    fun show(context: Context, users: List<UserEntity>, onPicked: (UserEntity) -> Unit) {
        val view = LayoutInflater.from(context).inflate(R.layout.dialog_user_picker, null)
        val search = view.findViewById<EditText>(R.id.editSearch)
        val list = view.findViewById<ListView>(R.id.listUsers)
        val empty = view.findViewById<TextView>(R.id.txtEmpty)

        val adapter = UserAdapter(context, users)
        list.adapter = adapter

        val dialog = AlertDialog.Builder(context)
            .setTitle(R.string.pick_user_title)
            .setView(view)
            .setNegativeButton(R.string.btn_cancel, null)
            .create()

        list.setOnItemClickListener { _, _, position, _ ->
            dialog.dismiss()
            onPicked(adapter.getItem(position))
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                adapter.filter(s?.toString().orEmpty())
                empty.visibility = if (adapter.count == 0) View.VISIBLE else View.GONE
            }
        })
        dialog.show()
    }

    private class UserAdapter(
        private val context: Context,
        private val all: List<UserEntity>,
    ) : BaseAdapter() {
        private var shown: List<UserEntity> = all

        fun filter(query: String) {
            val q = query.trim()
            shown = if (q.isEmpty()) {
                all
            } else {
                all.filter {
                    it.fullName.contains(q, ignoreCase = true) ||
                        it.userId.contains(q) ||
                        it.unit.contains(q, ignoreCase = true)
                }
            }
            notifyDataSetChanged()
        }

        override fun getCount() = shown.size
        override fun getItem(position: Int) = shown[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val row = convertView
                ?: LayoutInflater.from(context).inflate(R.layout.row_user, parent, false)
            val user = shown[position]
            row.findViewById<TextView>(R.id.txtUserName).text = user.fullName
            row.findViewById<TextView>(R.id.txtUserDetails).text =
                context.getString(R.string.user_row_details, user.userId, user.unit)
            return row
        }
    }
}

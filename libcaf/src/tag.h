#ifndef TAG_H
#define TAG_H

#include <string>
#include <ctime>
#include <optional>

class Tag {
public:
    const std::string object_hash;  // Hash of the object being tagged
    const std::string type;         // Type of the object (e.g., "commit", "tree", "blob")
    const std::string tag_name;     // Name of the
    const std::string author;     // Author of the tag
    const std::string message;    // tag message
    const std::time_t timestamp;  // Timestamp of the tag

    tag(const std::string& object_hash, const std::string& type,const std::string& tag_name, const std::string& author, const std::string& message, std::time_t timestamp,):
            object_hash(object_hash), type(type), tag_name(tag_name), author(author), message(message), timestamp(timestamp) {}
};

#endif // TAG_H
